from compute_output.sharktrack_annotations import yolo2sharktrack, extract_track_max_conf_detection, build_detection_folder
from argparse import ArgumentParser
from ultralytics import YOLO
import cv2
import os

class Model():
  def __init__(self, mobile=False):
    """
    Args:
      mobile (bool): Whether to use lightweight model developed to run quickly on CPU
    
    Model types:
    | Type    |  Model  | Fps  |
    |---------|---------|------|
    | mobile  | Yolov8n | 2fps |
    | analyst | Yolov8s | 5fps |
    """
    mobile_model = "/vol/biomedic3/bglocker/ugproj2324/fv220/dev/SharkTrack-Dev/models/yolov8_n_mvd2_50/best.pt"
    analyst_model = "/vol/biomedic3/bglocker/ugproj2324/fv220/dev/SharkTrack-Dev/models/p2v5_new/weights/best.pt"

    if mobile:
      self.model_path = mobile_model
      self.tracker_path = "botsort.yaml"
      self.device = "cpu"
      self.fps = 2
    else:
      self.model_path = analyst_model
      self.tracker_path = "./trackers/tracker_5fps.yaml"
      self.device = "0"
      self.fps = 5
    
    # Static Hyperparameters
    self.conf_threshold = 0.2
    self.iou_association_threshold = 0.5
    self.imgsz = 640

  
  def _get_frame_skip(self, video_path):
    cap = cv2.VideoCapture(video_path)  
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_skip = round(actual_fps / self.fps)
    return frame_skip


  def _postprocess(self, results):
      """
      Implements the following postprocessing steps:
      5fps:
          1. Extracts tracks that last for less than 1s (5frames)
          2. Removes the track if the max confidence is less than MAX_CONF_THRESHOLD
      """
      MAX_CONF_THRESHOLD = 0.8
      DURATION_THRESH = 5 if self.fps == 5 else 2

      track_counts = results["track_id"].value_counts()
      max_conf = results.groupby("track_id")["confidence"].max()
      valid_track_ids = track_counts[(track_counts >= DURATION_THRESH) | (max_conf > MAX_CONF_THRESHOLD)].index
      filtered_df = results[results["track_id"].isin(valid_track_ids)]

      return filtered_df

  
  def save(self, results, output_path="./output"):
    os.makedirs(output_path, exist_ok=True)

    sharktrack_results = yolo2sharktrack(results, self.fps)

    print(f"Postprocessing results...")
    sharktrack_results = self._postprocess(sharktrack_results)

    # Construct Detections Folder
    build_detection_folder(sharktrack_results, self.videos_folder, output_path, self.fps)

    # Save results to csv
    output_csv = os.path.join(output_path, "output.csv")
    print(f"Saving results to {output_csv}...")
    sharktrack_results.to_csv(output_csv, index=False)

  
  def track(self, video_path):
    print(f"Processing video: {video_path}...")
    model = YOLO(self.model_path)

    results = model.track(
      video_path,
      conf=self.conf_threshold,
      iou=self.iou_association_threshold,
      imgsz=self.imgsz,
      tracker=self.tracker_path,
      vid_stride=self._get_frame_skip(video_path),
      device=self.device,
      verbose=False,
    )

    return results


  def run(self, videos_folder, stereo=False, save_results=True):
    all_results = {}
    self.videos_folder = videos_folder

    for video in os.listdir(videos_folder):
      video_path = os.path.join(videos_folder, video)
      if os.path.isdir(video_path):
        for chapter in os.listdir(video_path):
          stereo_filter = not stereo or "LGX" in chapter # pick only left camera
          if chapter.endswith(".mp4") and stereo_filter:
            chapter_id = os.path.join(video, chapter)
            chapter_path = os.path.join(videos_folder, chapter_id)
            chapter_results = self.track(chapter_path)
            all_results[chapter_id] = chapter_results

    self.results = all_results
    if save_results:
      self.save(all_results)

    if len(all_results) == 0:
      print("No chapters found in the given folder")
      print("Please ensure the folder structure resembles the following:")
      print("videos_folder")
      print("├── video1")
      print("│   ├── chapter1.mp4")
      print("│   ├── chapter2.mp4")
      print("└── video2")
      print("    ├── chapter1.mp4")
      print("    ├── chapter2.mp4")

    return all_results

  def get_results(self):
    # 2. From the results construct VIAME
    return self.results

def main(video_path, stereo):
  model = Model()
  results = model.run(video_path, stereo=stereo)
  
  # 1. Run tracker with configs
  # 2. From the results construct VIAME


if __name__ == "__main__":
  parser = ArgumentParser()
  parser.add_argument("--video_path", type=str, required=True, help="Path to the video file")
  parser.add_argument("--stereo", type=bool, required=True, help="Whether folder contains stereo BRUVS (LGX/RGX)")
  args = parser.parse_args()
  main(args.video_path, args.stereo)
"""Readiness checks that do not need the physical camera or a trained model."""

import unittest

from rack_ai.final_pond.worker import FinalPondWorker
from rack_ai.registry import CAMERA_BY_ID
from rack_ai.worker_runtime import WorkerRuntimeRegistry


class FinalPondReadinessTests(unittest.TestCase):
    def test_camera_online_without_helmet_model_runs_presence_only(self):
        """Without a helmet model only the work-area task is live; the helmet task must not
        claim to run. The camera is live because watching the work area is real AI output."""
        worker = FinalPondWorker(camera_id="final-pond-cam-01", vision=object(),
                                 helmet_model_ready=False)
        status = WorkerRuntimeRegistry(stale_seconds=15).update(
            CAMERA_BY_ID["final-pond-cam-01"],
            worker.heartbeat(camera_online=True, camera_fps=15, inference_fps=3,
                             model_version="yolo11n.pt"),
        )
        self.assertEqual(status["camera_status"], "online")
        self.assertEqual(status["data_status"], "live")
        presence_task = next(task for task in status["tasks"] if task["task_id"] == "work-area-presence")
        self.assertEqual(presence_task["runtime_status"], "running")
        helmet_task = next(task for task in status["tasks"] if task["task_id"] == "ppe-helmet")
        self.assertEqual(helmet_task["runtime_status"], "unavailable")
        self.assertIsNone(helmet_task["model_version"])
        self.assertIsNone(helmet_task["latest"])

    def test_camera_and_helmet_model_together_can_report_running(self):
        worker = FinalPondWorker(camera_id="final-pond-cam-01", vision=object(),
                                 helmet_model_ready=True)
        status = WorkerRuntimeRegistry(stale_seconds=15).update(
            CAMERA_BY_ID["final-pond-cam-01"],
            worker.heartbeat(camera_online=True, camera_fps=15, inference_fps=3,
                             model_version="helmet.pt"),
        )
        self.assertEqual(status["data_status"], "live")

    def test_camera_offline_never_reports_helmet_running(self):
        worker = FinalPondWorker(camera_id="final-pond-cam-01", vision=object(),
                                 helmet_model_ready=True)
        heartbeat = worker.heartbeat(camera_online=False, camera_fps=0, inference_fps=0,
                                     model_version="helmet.pt")
        for task in heartbeat["tasks"]:
            self.assertEqual(task["runtime_status"], "unavailable", task["task_id"])


if __name__ == "__main__":
    unittest.main()

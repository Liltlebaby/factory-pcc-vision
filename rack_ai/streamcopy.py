"""Exclusive FFmpeg main-stream owner; never shares that source with OpenCV."""
import json
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone

from .recording import OpenCVRecorder, RecordingAudit
from .camera import RTSPReader

log = logging.getLogger('rack.streamcopy')


class FFmpegRecorder(OpenCVRecorder):
    def __init__(self, *args, source_url, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_url = source_url

    def _run(self, clip_id, duration, name, first, annotated=False, source='manual'):
        started = time.monotonic()
        value = dict(clip_id=clip_id,camera='Camera09',name=name,source=source,
                     start_time=datetime.now(timezone.utc).isoformat(),status='recording',
                     requested_duration_seconds=duration,file_path=f'raw/{clip_id}.mp4',
                     raw=True,encoder='ffmpeg_stream_copy',
                     note='Main stream copy; AI observations and annotated video use AI stream wall-clock window.')
        audit = RecordingAudit(self.provider,self.store.root,clip_id,annotated)
        process = None
        error = None
        path = self.store.root/value['file_path']
        try:
            self.store.save(value)
            command = [shutil.which('ffmpeg'),'-hide_banner','-loglevel','error']
            if self.source_url.startswith(('rtsp://','rtsps://')):
                command += ['-rtsp_transport','tcp','-timeout','5000000']
            else:
                command += ['-re']  # local fixture playback at original rate
            command += ['-i',self.source_url,'-t',str(duration),'-map','0:v:0','-an',
                        '-c:v','copy','-movflags','+frag_keyframe+empty_moov','-n',str(path)]
            # Never log command/stderr: both may contain camera credentials.
            process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            size, last_growth = 0, time.monotonic()
            log.info('recording_started clip_id=%s encoder=stream_copy',clip_id)
            while process.poll() is None:
                now = time.monotonic()
                audit.sample()
                with self.lock:
                    self.state['elapsed_seconds'] = round(now-started,2)
                current = path.stat().st_size if path.exists() else 0
                if current > size:
                    size, last_growth = current, now
                if self.stop_event.is_set():
                    break
                if now-started > duration+20 or now-last_growth > 20:
                    raise RuntimeError('stream_copy_timeout')
                if shutil.disk_usage(self.store.root).free < 100*1024**2:
                    raise RuntimeError('disk_space_low')
                self.stop_event.wait(.1)
            if self.stop_event.is_set() and process.poll() is None:
                process.stdin.write(b'q\n')
                process.stdin.flush()
            code = process.wait(timeout=6)
            if code != 0:
                raise RuntimeError('stream_copy_failed')
            # Validate only the completed local file; no second RTSP connection.
            check = subprocess.run([shutil.which('ffprobe'),'-v','error','-select_streams','v:0',
                '-show_entries','stream=width,height,r_frame_rate:format=duration','-of','json',str(path)],
                capture_output=True,timeout=10,check=True,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            probe = json.loads(check.stdout)
            stream = probe['streams'][0]
            seconds = float(probe['format']['duration'])
            if seconds <= 0:
                raise RuntimeError('empty_clip')
            if not self.stop_event.is_set() and seconds < duration-2:
                raise RuntimeError('clip_ended_early')
            value.update(resolution=f"{stream['width']}x{stream['height']}",
                         fps_fraction=stream['r_frame_rate'],video_duration_seconds=seconds,
                         status='stopped' if self.stop_event.is_set() else 'recorded')
        except Exception as exc:
            error = str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
            value['status'] = 'failed'
            log.error('stream_copy_failed clip_id=%s error_type=%s',clip_id,type(exc).__name__)
        finally:
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdin:
                    process.stdin.close()
            value.update(audit.close())
            value.update(end_time=datetime.now(timezone.utc).isoformat(),duration_seconds=time.monotonic()-started,error=error)
            # The FFmpeg process has exited before the fallback reader can open
            # this source. Preserve the failed attempt rather than overwriting it.
            if error == 'stream_copy_failed' and not self.stop_event.is_set():
                try:
                    failed_path = f'raw/{clip_id}_copy_failed.mp4'
                    if path.exists():
                        path.rename(self.store.root/failed_path)
                        value['file_path'] = failed_path
                    self.fallback_note = dict(reason=error,copy_attempt_file=failed_path,
                                              restarted_full_duration=True)
                    reader = RTSPReader(self.source_url,retry=3)
                    reader.start()
                    try:
                        until = time.monotonic()+8
                        packet = None
                        while time.monotonic() < until and not self.stop_event.is_set():
                            packet = reader.buffer.get()
                            if packet is not None:
                                break
                            self.stop_event.wait(.1)
                        if packet is not None and not self.stop_event.is_set():
                            original = self.buffer
                            self.buffer = reader.buffer
                            try:
                                super()._run(clip_id,duration,name,packet,annotated,source)
                            finally:
                                self.buffer = original
                            return
                    finally:
                        reader.close()
                except Exception as exc:
                    error = 'copy_and_fallback_failed'
                    log.error('recording_fallback_failed type=%s',type(exc).__name__)
            value['error'] = error
            try:
                self.store.save(value)
            except Exception:
                value['status'], error = 'failed','metadata_save_failed'
            with self.lock:
                self.state.update(active=False,status=value['status'],error=error)

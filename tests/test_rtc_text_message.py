import asyncio
import json
import logging
import os
import random
import string
import sys
from collections import deque

import numpy as np
import requests

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class VideoSaver:
    """视频保存器"""
    def __init__(self, output_dir="output_videos"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.frame_count = 0
        self.frames = deque(maxlen=600)  # 最多保存20秒 (30fps)
        self.fps = 30
        
    def save_frame(self, frame):
        """接收视频帧并保存"""
        if hasattr(frame, 'to_ndarray'):
            frame_array = frame.to_ndarray()
        elif isinstance(frame, np.ndarray):
            frame_array = frame
        else:
            return
            
        self.frames.append(frame_array)
        self.frame_count += 1
        
        if self.frame_count % 30 == 0:
            logger.info(f"已保存 {self.frame_count} 帧")
    
    def save_video(self, filename=None):
        """将保存的帧保存为视频文件"""
        if len(self.frames) == 0:
            logger.warning("没有视频帧可保存")
            return
            
        if filename is None:
            filename = os.path.join(self.output_dir, f"video_{random.randint(1000,9999)}.mp4")
        
        try:
            import cv2
            
            first_frame = self.frames[0]
            if len(first_frame.shape) == 3:
                height, width = first_frame.shape[:2]
            else:
                height, width = 480, 640
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(filename, fourcc, self.fps, (width, height))
            
            for frame in self.frames:
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                else:
                    frame_bgr = frame
                out.write(frame_bgr)
            
            out.release()
            logger.info(f"视频已保存到: {filename}")
            logger.info(f"总帧数: {len(self.frames)}, 时长: {len(self.frames)/self.fps:.2f}秒")
            
        except Exception as e:
            logger.exception(f"保存视频失败: {e}")


class AudioSaver:
    """音频保存器"""
    def __init__(self, output_dir="output_videos"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.audio_data = []
        self.sample_rate = 24000
        self.channels = 1
        
    def save_frame(self, frame):
        """接收音频帧并保存"""
        try:
            if hasattr(frame, 'to_ndarray'):
                audio_array = frame.to_ndarray()
            elif isinstance(frame, np.ndarray):
                audio_array = frame
            else:
                return
            
            if audio_array is not None:
                self.audio_data.append(audio_array)
                logger.debug(f"已保存音频帧, 形状: {audio_array.shape}")
        except Exception as e:
            logger.exception(f"保存音频帧失败: {e}")
    
    def save_audio(self, filename=None):
        """将保存的音频保存为 WAV 文件"""
        if len(self.audio_data) == 0:
            logger.warning("没有音频数据可保存")
            return
            
        try:
            import wave
            
            if filename is None:
                filename = os.path.join(self.output_dir, f"audio_{random.randint(1000,9999)}.wav")
            
            # 合并所有音频帧
            audio_combined = np.concatenate(self.audio_data, axis=-1)
            
            # 确保是单声道
            if len(audio_combined.shape) > 1:
                audio_combined = audio_combined.mean(axis=0)
            
            # 转换为 16-bit PCM
            audio_int16 = (audio_combined * 32767).astype(np.int16)
            
            # 保存为 WAV
            with wave.open(filename, 'w') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_int16.tobytes())
            
            duration = len(audio_int16) / self.sample_rate
            logger.info(f"音频已保存到: {filename}")
            logger.info(f"音频时长: {duration:.2f}秒")
            
        except Exception as e:
            logger.exception(f"保存音频失败: {e}")


async def test_rtc_text_message():
    """测试RTC文字消息发送 - 模拟前端方式"""
    logger.info("开始RTC文字消息测试...")

    server_url = "https://localhost:8282"
    timeout = 30
    
    # 创建音视频保存器
    video_saver = VideoSaver("output_videos")
    audio_saver = AudioSaver("output_videos")

    # 1. 获取配置
    try:
        logger.info(f"正在连接服务器 {server_url}...")
        response = requests.get(f"{server_url}/openavatarchat/initconfig", verify=False, timeout=timeout)
        if response.status_code == 200:
            config = response.json()
            logger.info("获取配置成功")
        else:
            logger.exception(f"获取配置失败: {response.status_code}")
            return
    except Exception as e:
        logger.exception("连接服务失败")
        return

    # 2. 创建 RTCPeerConnection
    try:
        rtc_config = RTCConfiguration()
        rtc_config.iceServers = []
        pc = RTCPeerConnection(rtc_config)
        logger.info("创建RTCPeerConnection成功")
    except Exception as e:
        logger.exception("创建RTCPeerConnection失败")
        return

    # 3. 创建 Data Channel
    try:
        data_channel = pc.createDataChannel('text')
        logger.info("创建数据通道成功")
    except Exception as e:
        logger.exception("创建数据通道失败")
        return

    # 生成 webrtc_id
    webrtc_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    logger.info(f"生成webrtc_id: {webrtc_id}")

    # 4. 注册事件回调
    def send_ice_candidate(candidate):
        try:
            candidate_data = {
                "candidate": {
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                },
                "webrtc_id": webrtc_id,
                "type": "ice-candidate"
            }
            response = requests.post(
                f"{server_url}/webrtc/offer",
                json=candidate_data,
                verify=False,
                timeout=timeout
            )
            if response.status_code == 200:
                logger.debug("发送ICE候选成功")
        except Exception as e:
            logger.exception("发送ICE候选异常")

    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        if candidate:
            logger.debug(f"ICE候选: {candidate.candidate[:50]}...")
            send_ice_candidate(candidate)

    @pc.on("track")
    def on_track(track):
        """接收远程轨道（服务端发送的视频/音频）"""
        logger.info(f"收到远程轨道: {track.kind}")
        
        if track.kind == "video":
            # 保存视频帧
            async def save_video_frames():
                logger.info("开始接收视频帧...")
                while True:
                    try:
                        frame = await track.recv()
                        video_saver.save_frame(frame)
                    except Exception as e:
                        logger.info(f"视频接收结束: {e}")
                        break
            asyncio.create_task(save_video_frames())
            
        elif track.kind == "audio":
            # 保存音频帧
            async def save_audio_frames():
                logger.info("开始接收音频帧...")
                while True:
                    try:
                        frame = await track.recv()
                        audio_saver.save_frame(frame)
                    except Exception as e:
                        logger.info(f"音频接收结束: {e}")
                        break
            asyncio.create_task(save_audio_frames())

    @data_channel.on("open")
    def on_open():
        logger.info("数据通道已打开")
        test_message = json.dumps({
            "type": "chat",
            "data": "Hello from test client!"
        })
        data_channel.send(test_message)
        logger.info("发送测试消息: Hello from test client!")

    @data_channel.on("message")
    def on_message(message):
        logger.info(f"收到消息: {message}")

    @data_channel.on("close")
    def on_close():
        logger.info("数据通道已关闭")

    # 5. 创建并设置 Local Description
    logger.info("正在创建offer...")
    try:
        offer = await asyncio.wait_for(pc.createOffer(), timeout=30)
        logger.info("创建offer成功")
    except Exception as e:
        logger.exception("创建offer失败")
        await pc.close()
        return

    try:
        await asyncio.wait_for(pc.setLocalDescription(offer), timeout=30)
        logger.info("设置本地描述成功")
    except Exception as e:
        logger.exception("设置本地描述失败")
        await pc.close()
        return

    # 6. 发送 Offer 到服务器
    logger.info("发送offer到服务器...")
    try:
        offer_data = {
            "sdp": offer.sdp,
            "type": offer.type,
            "webrtc_id": webrtc_id
        }
        response = requests.post(
            f"{server_url}/webrtc/offer",
            json=offer_data,
            verify=False,
            timeout=timeout
        )
        if response.status_code == 200:
            answer = response.json()
            logger.info("收到服务器的answer")
            
            await asyncio.wait_for(pc.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type=answer['type'])), timeout=30)
            logger.info("设置远程描述成功")
        else:
            logger.exception(f"发送offer失败: {response.status_code}")
            await pc.close()
            return
    except Exception as e:
        logger.exception("发送offer异常")
        await pc.close()
        return

    # 7. 等待音视频接收
    logger.info("等待接收服务端音视频（15秒）...")
    try:
        await asyncio.sleep(15)
    except Exception as e:
        logger.exception("等待异常")

    logger.info(f"ICE连接状态: {pc.iceConnectionState}")
    logger.info(f"Data Channel状态: {data_channel.readyState}")

    # 8. 检查连接状态，如果成功则发送消息
    if data_channel.readyState == "open":
        logger.info("Data Channel 已打开，发送测试消息...")
        test_message = json.dumps({
            "type": "chat",
            "data": "Hello from test client!"
        })
        data_channel.send(test_message)
        
        # 再等待一段时间接收响应
        logger.info("等待接收响应（10秒）...")
        await asyncio.sleep(10)
    else:
        logger.warning(f"Data Channel 未打开，当前状态: {data_channel.readyState}")

    # 9. 保存音视频
    logger.info("正在保存视频...")
    video_saver.save_video()
    
    logger.info("正在保存音频...")
    audio_saver.save_audio()

    # 10. 关闭连接
    logger.info("关闭连接...")
    try:
        await pc.close()
        logger.info("连接已关闭")
    except Exception as e:
        logger.exception("关闭连接异常")

    logger.info("测试完成！")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    asyncio.run(test_rtc_text_message())

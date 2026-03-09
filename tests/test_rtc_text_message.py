import asyncio
import json
import logging
import time

import requests
import random
import string
import sys
import numpy as np
import av
from fractions import Fraction

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration
from aiortc.mediastreams import VideoStreamTrack, AudioStreamTrack
from av import VideoFrame, AudioFrame

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class BlackVideoTrack(VideoStreamTrack):
    """黑色视频轨道 - 模拟摄像头输入"""
    def __init__(self):
        super().__init__()
        self.kind = "video"
        self._pts = 0
        self._sample_rate = 48000
        self._samples_per_frame = 960  # 20ms

    async def recv(self):
        # 生成 640x480 黑色视频帧
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        
        video_frame.pts = self._pts
        video_frame.time_base = Fraction(1, 30)  # 30fps
        self._pts += 1
        
        return video_frame


class SilentAudioTrack(AudioStreamTrack):
    """静音音频轨道 - 模拟麦克风输入"""
    def __init__(self):
        super().__init__()
        self.kind = "audio"
        self._pts = 0
        self._sample_rate = 48000
        self._samples_per_frame = 960  # 20ms

    async def recv(self):
        # 生成静音数据：形状 (960,) 的 int16 数组（单声道 packed）
        samples = np.zeros((1, self._samples_per_frame), dtype=np.int16)
        # 或者使用浮点格式 samples = np.zeros(self._samples_per_frame, dtype=np.float32)

        audio_frame = av.AudioFrame.from_ndarray(
            samples,
            format="s16",  # 如果使用浮点，改为 "flt"
            layout="mono"
        )
        audio_frame.sample_rate = self._sample_rate  # 关键：必须设置！
        audio_frame.pts = self._pts
        audio_frame.time_base = Fraction(1, self._sample_rate)

        self._pts += self._samples_per_frame
        return audio_frame


async def test_rtc_text_message():
    """测试RTC文字消息发送 - 模拟前端方式"""
    logger.info("开始RTC文字消息测试...")

    server_url = "https://localhost:8282"
    timeout = 30

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

    # 3. 创建本地音视频轨道
    video_track = BlackVideoTrack()
    audio_track = SilentAudioTrack()

    # 4. 添加轨道到 RTCPeerConnection
    try:
        video_sender = pc.addTrack(video_track)
        audio_sender = pc.addTrack(audio_track)
        logger.info(f"添加音视频轨道成功 - video sender: {video_sender}, audio sender: {audio_sender}")
    except Exception as e:
        logger.exception("添加音视频轨道失败")
        return

    # 5. 创建 Data Channel
    try:
        data_channel = pc.createDataChannel('text')
        logger.info("创建数据通道成功")
    except Exception as e:
        logger.exception("创建数据通道失败")
        return

    # 生成 webrtc_id
    webrtc_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    logger.info(f"生成webrtc_id: {webrtc_id}")

    # 6. 注册事件回调
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
        logger.info(f"收到远程轨道: {track.kind}")
        
        async def play_track():
            if track.kind == "video":
                logger.info(f"开始接收视频轨道: {track.id}")
                while True:
                    try:
                        frame = await track.recv()
                        # 处理视频帧
                        logger.info(f"收到视频帧: width={frame.width}, height={frame.height}")
                        # 可以在这里保存视频帧或进行其他处理
                    except Exception as e:
                        logger.error(f"视频轨道错误: {e}")
                        break
            elif track.kind == "audio":
                logger.info(f"开始接收音频轨道: {track.id} {track.sample_rate}")
                # 初始化音频保存
                import wave
                import os
                import numpy as np
                
                # 创建保存目录
                output_dir = "audio_output"
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                
                # 音频文件路径
                audio_file = os.path.join(output_dir, f"received_audio_{int(time.time())}.wav")
                
                # 音频参数
                sample_rate = 24000  # 假设采样率为48kHz
                channels = 1  # 单声道
                sample_width = 2  # 16位
                
                # 打开WAV文件
                wf = wave.open(audio_file, 'wb')
                wf.setnchannels(channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                
                logger.info(f"开始保存音频到: {audio_file}")
                
                try:
                    while True:
                        frame = await track.recv()
                        # 处理音频帧
                        logger.info(f"收到音频帧: samples={frame.samples}, samples.dtype={frame.to_ndarray().dtype}")
                        logger.info(f"收到音频帧: samples={frame.samples}, samples.dtype={frame.to_ndarray()}")
                        
                        # 将音频帧转换为numpy数组
                        samples = frame.to_ndarray()
                        
                        # 确保数据格式正确
                        if samples.dtype == np.float32:
                            # 转换为16位整数
                            samples = np.int16(samples * 32767)
                        elif samples.dtype != np.int16:
                            # 其他格式转换为16位整数
                            samples = np.int16(samples)
                        
                        # 确保是一维数组
                        if samples.ndim > 1:
                            samples = samples.flatten()
                        
                        # 写入WAV文件
                        wf.writeframes(samples.tobytes())
                        
                except Exception as e:
                    logger.error(f"音频轨道错误: {e}")
                finally:
                    # 关闭WAV文件
                    wf.close()
                    logger.info(f"音频保存完成: {audio_file}")
        
        # 启动异步任务处理轨道
        asyncio.create_task(play_track())

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

    # 7. 创建并设置 Local Description
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

    # 8. 发送 Offer 到服务器
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

    # 9. 等待 ICE 连接建立
    logger.info("等待ICE连接建立（5秒）...")
    try:
        await asyncio.sleep(100)
    except Exception as e:
        logger.exception("等待异常")

    logger.info(f"ICE连接状态: {pc.iceConnectionState}")
    logger.info(f"Data Channel状态: {data_channel.readyState}")

    # 10. 检查连接状态，如果成功则发送消息
    if data_channel.readyState == "open":
        logger.info("Data Channel 已打开，发送测试消息...")
        test_message = json.dumps({
            "type": "chat",
            "data": "Hello from test client!"
        })
        data_channel.send(test_message)
        await asyncio.sleep(50)
    else:
        logger.warning(f"Data Channel 未打开，当前状态: {data_channel.readyState}")


    # 10. 等待一段时间接收数据
    logger.info("等待接收数据（100秒）...")
    await asyncio.sleep(100)
    
    # 11. 关闭连接
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

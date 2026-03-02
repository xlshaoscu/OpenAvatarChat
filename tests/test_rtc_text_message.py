import asyncio
import json
import logging
import requests
import random
import string
import sys
import numpy as np
import av

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

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        # 生成 640x480 黑色视频帧
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


class SilentAudioTrack(AudioStreamTrack):
    """静音音频轨道 - 模拟麦克风输入"""
    def __init__(self):
        super().__init__()
        self.kind = "audio"

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        # 生成静音音频帧 (48000Hz, 20ms = 960 samples)
        frame = np.zeros(960, dtype=np.int16)
        audio_frame = AudioFrame.from_ndarray(frame, format="s16", layout="mono")
        audio_frame.pts = pts
        audio_frame.time_base = time_base
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

    # 2. 创建 RTCPeerConnection (模拟前端: new RTCPeerConnection())
    try:
        rtc_config = RTCConfiguration()
        rtc_config.iceServers = []
        pc = RTCPeerConnection(rtc_config)
        logger.info("创建RTCPeerConnection成功")
    except Exception as e:
        logger.exception("创建RTCPeerConnection失败")
        return

    # 3. 创建本地音视频轨道 (模拟前端: navigator.mediaDevices.getUserMedia())
    video_track = BlackVideoTrack()
    audio_track = SilentAudioTrack()

    # 4. 添加轨道到 RTCPeerConnection (模拟前端: pc.addTrack(track, stream))
    try:
        video_sender = pc.addTrack(video_track)
        audio_sender = pc.addTrack(audio_track)
        logger.info(f"添加音视频轨道成功 - video sender: {video_sender}, audio sender: {audio_sender}")
    except Exception as e:
        logger.exception("添加音视频轨道失败")
        return

    # 5. 创建 Data Channel (模拟前端: pc.createDataChannel('text'))
    try:
        data_channel = pc.createDataChannel('text')
        logger.info("创建数据通道成功")
    except Exception as e:
        logger.exception("创建数据通道失败")
        return

    # 生成 webrtc_id (模拟前端)
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

    @data_channel.on("open")
    def on_open():
        logger.info("数据通道已打开")
        # 7. 发送测试消息 (模拟前端发送文字)
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

    # 8. 创建并设置 Local Description (模拟前端: pc.createOffer() + pc.setLocalDescription())
    logger.info("正在创建offer...")
    try:
        offer = await asyncio.wait_for(pc.createOffer(), timeout=30)
        logger.info("创建offer成功")
        
        # 检查 SDP 中是否包含轨道信息
        if "m=video" in offer.sdp:
            logger.info("SDP 包含视频轨道")
        if "m=audio" in offer.sdp:
            logger.info("SDP 包含音频轨道")
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

    # 9. 发送 Offer 到服务器 (模拟前端: fetch('/webrtc/offer', ...))
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
            
            # 10. 设置远程描述 (模拟前端: pc.setRemoteDescription(answer))
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

    # 11. 等待 ICE 连接建立 (模拟前端等待连接成功)
    logger.info("等待ICE连接建立（5秒）...")
    try:
        await asyncio.sleep(5)
    except Exception as e:
        logger.exception("等待异常")

    logger.info(f"ICE连接状态: {pc.iceConnectionState}")
    logger.info(f"Data Channel状态: {data_channel.readyState}")

    # 12. 检查连接状态，如果成功则发送消息
    if data_channel.readyState == "open":
        logger.info("Data Channel 已打开，发送测试消息...")
        test_message = json.dumps({
            "type": "chat",
            "data": "Hello from test client!"
        })
        data_channel.send(test_message)
        await asyncio.sleep(2)
    else:
        logger.warning(f"Data Channel 未打开，当前状态: {data_channel.readyState}")

    # 13. 关闭连接
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

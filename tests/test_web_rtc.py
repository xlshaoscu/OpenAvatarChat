import asyncio
import json
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRecorder
import aiohttp
import time
import ssl  # 导入 ssl 模块


class TestAudioTrack(MediaStreamTrack):
    """测试音频轨道"""
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.sample_rate = 16000
        self.samples_per_frame = 160  # 10ms per frame

    async def recv(self):
        # 生成正弦波音频
        t = time.time()
        samples = np.arange(self.samples_per_frame)
        waveform = np.sin(2 * np.pi * 440 * (t + samples / self.sample_rate))
        frame = (waveform * 32767).astype(np.int16)
        return frame.tobytes()


class TestVideoTrack(MediaStreamTrack):
    """测试视频轨道"""
    kind = "video"

    def __init__(self):
        super().__init__()
        self.width = 640
        self.height = 480
        self.fps = 30

    async def recv(self):
        # 生成测试视频帧（红色背景）
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :, 0] = 255  # 红色
        return frame


async def test_webrtc_client():
    """测试WebRTC客户端"""
    print("开始WebRTC测试...")

    # 1. 获取初始化配置
    # 创建不验证SSL证书的SSL上下文
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False  # 禁用主机名检查
    ssl_context.verify_mode = ssl.CERT_NONE  # 禁用证书验证

    # 1. 获取初始化配置
    async with aiohttp.ClientSession(ssl=ssl_context) as session:
        try:
            async with session.get("http://localhost:8282/openavatarchat/initconfig") as response:
                if response.status == 200:
                    config = await response.json()
                    print("✓ 获取配置成功")
                    print(f"  RTC配置: {config.get('rtc_configuration', 'No RTC config')}")
                else:
                    print(f"✗ 获取配置失败: {response.status}")
                    return
        except Exception as e:
            print(f"✗ 连接服务失败: {e}")
            return

    # 2. 创建RTCPeerConnection
    pc = RTCPeerConnection()
    print("✓ 创建RTCPeerConnection成功")

    # 3. 添加媒体轨道
    audio_track = TestAudioTrack()
    video_track = TestVideoTrack()
    pc.addTrack(audio_track)
    pc.addTrack(video_track)
    print("✓ 添加媒体轨道成功")

    # 4. 处理远程流
    @pc.on("track")
    def on_track(track):
        print(f"✓ 收到远程轨道: {track.kind}")
        if track.kind == "audio":
            print("  - 远程音频轨道")
        elif track.kind == "video":
            print("  - 远程视频轨道")

    # 5. 处理数据通道
    data_channel = pc.createDataChannel("chat")

    @data_channel.on("open")
    def on_open():
        print("✓ 数据通道已打开")
        # 发送测试消息
        data_channel.send(json.dumps({
            "type": "chat",
            "data": "Hello from test client!"
        }))
        print("✓ 发送测试消息")

    @data_channel.on("message")
    def on_message(message):
        print(f"✓ 收到消息: {message}")

    @data_channel.on("close")
    def on_close():
        print("✗ 数据通道已关闭")

    # 6. 处理ICE候选
    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        if candidate:
            print(f"  ICE候选: {candidate.candidate[:50]}...")

    # 7. 创建offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("✓ 创建offer成功")
    print(f"  Offer SDP长度: {len(offer.sdp)}")

    # 8. 模拟信令交换（实际项目中需要通过WebSocket发送）
    print("模拟信令交换...")
    await asyncio.sleep(1)

    # 9. 保持连接
    print("测试连接中...")
    try:
        # 保持连接10秒
        for i in range(10):
            print(f"  连接保持中... {i + 1}/10")
            await asyncio.sleep(1)

            # 每隔2秒发送一条消息
            if (i + 1) % 2 == 0:
                if data_channel.readyState == "open":
                    data_channel.send(json.dumps({
                        "type": "chat",
                        "data": f"Test message {i + 1}"
                    }))
                    print(f"  ✓ 发送消息 {i + 1}")
    except KeyboardInterrupt:
        print("\n用户中断测试")

    # 10. 关闭连接
    print("关闭连接...")
    await pc.close()
    print("✓ 连接已关闭")
    print("测试完成！")


if __name__ == "__main__":
    asyncio.run(test_webrtc_client())
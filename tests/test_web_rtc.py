import asyncio
import json
from aiortc import RTCPeerConnection, RTCSessionDescription
import aiohttp
import time
import ssl  # 导入 ssl 模块


async def test_webrtc_client():
    """测试WebRTC客户端 - 仅发送文字消息"""
    print("开始WebRTC测试...")

    # 服务配置
    server_url = "https://localhost:8282"
    ws_url = "wss://localhost:8282"

    # 1. 获取初始化配置
    connector = aiohttp.TCPConnector(ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(f"{server_url}/openavatarchat/initconfig") as response:
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

    # 2. 创建RTCPeerConnection - 使用默认配置
    pc = RTCPeerConnection()
    print("✓ 创建RTCPeerConnection成功")

    # 3. 处理数据通道
    data_channel = pc.createDataChannel("chat")

    @data_channel.on("open")
    def on_open():
        print("✓ 数据通道已打开")
        # 发送测试消息
        test_message = json.dumps({
            "type": "chat",
            "data": "Hello from test client!"
        })
        data_channel.send(test_message)
        print("✓ 发送测试消息: Hello from test client!")

    @data_channel.on("message")
    def on_message(message):
        print(f"✓ 收到消息: {message}")

    @data_channel.on("close")
    def on_close():
        print("✗ 数据通道已关闭")

    # 4. 处理ICE候选
    ice_candidates = []
    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        if candidate:
            ice_candidates.append(candidate)
            print(f"  ICE候选: {candidate.candidate[:50]}...")

    # 5. 创建offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("✓ 创建offer成功")

    # 6. 实际信令交换（通过WebSocket）
    print("开始信令交换...")
    try:
        # 创建WebSocket连接
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.ws_connect(f"{ws_url}/ws") as ws:
                print("✓ WebSocket连接成功")
                
                # 发送offer
                offer_data = {
                    "type": "offer",
                    "sdp": offer.sdp
                }
                await ws.send_json(offer_data)
                print("✓ 发送offer到服务器")
                
                # 接收answer
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "answer":
                            print("✓ 收到服务器的answer")
                            answer = RTCSessionDescription(sdp=data["sdp"], type="answer")
                            await pc.setRemoteDescription(answer)
                            print("✓ 设置远程描述成功")
                            
                            # 发送ICE候选
                            for candidate in ice_candidates:
                                candidate_data = {
                                    "type": "ice-candidate",
                                    "candidate": candidate.candidate,
                                    "sdpMid": candidate.sdpMid,
                                    "sdpMLineIndex": candidate.sdpMLineIndex
                                }
                                await ws.send_json(candidate_data)
                            print("✓ 发送ICE候选到服务器")
                            break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"✗ WebSocket错误: {msg.data}")
                        break
    except Exception as e:
        print(f"✗ 信令交换失败: {e}")
        # 继续执行，即使信令交换失败

    # 7. 保持连接
    print("测试连接中...")
    try:
        # 保持连接5秒，确保消息发送
        for i in range(5):
            print(f"  连接保持中... {i + 1}/5")
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n用户中断测试")

    # 8. 关闭连接
    print("关闭连接...")
    await pc.close()
    print("✓ 连接已关闭")
    print("测试完成！")


if __name__ == "__main__":
    asyncio.run(test_webrtc_client())

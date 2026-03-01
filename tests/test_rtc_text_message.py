import asyncio
import json
import logging
import requests
import time
import random
import string

from aiortc import RTCPeerConnection, RTCSessionDescription

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_rtc_text_message():
    """测试RTC文字消息发送"""
    logger.info("开始RTC文字消息测试...")

    # 服务配置
    server_url = "https://localhost:8282"

    # 1. 获取初始化配置
    try:
        response = requests.get(f"{server_url}/openavatarchat/initconfig", verify=False)
        if response.status_code == 200:
            config = response.json()
            logger.info("获取配置成功")
            logger.info(f"RTC配置: {config.get('rtc_configuration', 'No RTC config')}")
        else:
            logger.error(f"获取配置失败: {response.status_code}")
            return
    except Exception as e:
        logger.exception("连接服务失败")
        return

    # 2. 创建RTCPeerConnection
    try:
        rtc_config = config.get('rtc_configuration', {})
        pc = RTCPeerConnection(rtc_config)
        logger.info("创建RTCPeerConnection成功")
    except Exception as e:
        logger.exception("创建RTCPeerConnection失败")
        return

    # 3. 创建数据通道
    try:
        data_channel = pc.createDataChannel('text')
        logger.info("创建数据通道成功")
    except Exception as e:
        logger.exception("创建数据通道失败")
        return

    # 4. 处理数据通道事件
    @data_channel.on("open")
    def on_open():
        logger.info("数据通道已打开")
        # 发送测试消息
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

    # 5. 处理ICE候选
    ice_candidates = []
    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        if candidate:
            ice_candidates.append(candidate)
            logger.debug(f"ICE候选: {candidate.candidate[:50]}...")
            # 发送ICE候选到服务器
            send_ice_candidate(candidate)

    # 6. 生成webrtc_id
    webrtc_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    logger.info(f"生成webrtc_id: {webrtc_id}")

    # 7. 发送ICE候选的函数
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
                verify=False
            )
            if response.status_code == 200:
                logger.debug("发送ICE候选成功")
            else:
                logger.error(f"发送ICE候选失败: {response.status_code}")
        except Exception as e:
            logger.exception("发送ICE候选异常")

    # 8. 创建offer
    try:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        logger.info("创建offer成功")
    except Exception as e:
        logger.exception("创建offer失败")
        return

    # 9. 发送offer到服务器
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
            verify=False
        )
        if response.status_code == 200:
            answer = response.json()
            logger.info("收到服务器的answer")
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type=answer['type']))
            logger.info("设置远程描述成功")
        else:
            logger.error(f"发送offer失败: {response.status_code}")
            return
    except Exception as e:
        logger.exception("发送offer异常")
        return

    # 10. 保持连接
    logger.info("测试连接中...")
    try:
        # 保持连接5秒，确保消息发送
        for i in range(5):
            logger.info(f"连接保持中... {i + 1}/5")
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("用户中断测试")
    except Exception as e:
        logger.exception("保持连接异常")

    # 11. 关闭连接
    logger.info("关闭连接...")
    try:
        pc.close()
        logger.info("连接已关闭")
    except Exception as e:
        logger.exception("关闭连接异常")

    logger.info("测试完成！请查看服务日志确认消息是否被处理。")

if __name__ == "__main__":
    # 禁用SSL验证警告
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    asyncio.run(test_rtc_text_message())
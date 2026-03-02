import asyncio
import json
import logging
import requests
import time
import random
import string

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_rtc_text_message():
    """测试RTC文字消息发送"""
    logger.info("开始RTC文字消息测试...")

    server_url = "https://localhost:8282"
    timeout = 5

    try:
        logger.info("正在连接服务器...")
        response = requests.get(f"{server_url}/openavatarchat/initconfig", verify=False, timeout=timeout)
        if response.status_code == 200:
            config = response.json()
            logger.info("获取配置成功")
            rtc_config_data = config.get('rtc_configuration', {})
            logger.info(f"原始RTC配置: {rtc_config_data}")
        else:
            logger.error(f"获取配置失败: {response.status_code}")
            return
    except requests.exceptions.ConnectionError:
        logger.error(f"无法连接到服务器 {server_url}，请确保服务已启动")
        return
    except requests.exceptions.Timeout:
        logger.error(f"连接服务器超时")
        return
    except Exception as e:
        logger.exception("连接服务失败")
        return

    try:
        rtc_config = RTCConfiguration()
        rtc_config.iceServers = []
        logger.info("使用空配置的RTCPeerConnection")
        pc = RTCPeerConnection(rtc_config)
        logger.info("创建RTCPeerConnection成功")
    except Exception as e:
        logger.exception("创建RTCPeerConnection失败")
        return

    try:
        data_channel = pc.createDataChannel('text')
        logger.info("创建数据通道成功")
    except Exception as e:
        logger.exception("创建数据通道失败")
        return

    ice_candidates = []
    webrtc_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    logger.info(f"生成webrtc_id: {webrtc_id}")

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
            else:
                logger.error(f"发送ICE候选失败: {response.status_code}")
        except Exception as e:
            logger.exception("发送ICE候选异常")

    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        if candidate:
            ice_candidates.append(candidate)
            logger.debug(f"ICE候选: {candidate.candidate[:50]}...")
            send_ice_candidate(candidate)

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

    logger.info("正在创建offer...")
    try:
        offer = await asyncio.wait_for(pc.createOffer(), timeout=10)
        logger.info("创建offer成功")
    except asyncio.TimeoutError:
        logger.error("创建offer超时")
        pc.close()
        return
    except Exception as e:
        logger.exception("创建offer失败")
        pc.close()
        return

    try:
        await asyncio.wait_for(pc.setLocalDescription(offer), timeout=10)
        logger.info("设置本地描述成功")
    except asyncio.TimeoutError:
        logger.error("设置本地描述超时")
        pc.close()
        return
    except Exception as e:
        logger.exception("设置本地描述失败")
        pc.close()
        return

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
            await asyncio.wait_for(pc.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type=answer['type'])), timeout=10)
            logger.info("设置远程描述成功")
        else:
            logger.error(f"发送offer失败: {response.status_code}")
            pc.close()
            return
    except asyncio.TimeoutError:
        logger.error("设置远程描述超时")
        pc.close()
        return
    except Exception as e:
        logger.exception("发送offer异常")
        pc.close()
        return

    logger.info("等待ICE连接建立（3秒）...")
    try:
        await asyncio.sleep(3)
    except Exception as e:
        logger.exception("等待异常")

    logger.info("关闭连接...")
    try:
        pc.close()
        logger.info("连接已关闭")
    except Exception as e:
        logger.exception("关闭连接异常")

    logger.info("测试完成！")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    asyncio.run(test_rtc_text_message())

import asyncio
import json
import logging
import requests
import random
import string
import sys

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def test_rtc_text_message():
    """测试RTC文字消息发送"""
    logger.info("开始RTC文字消息测试...")

    server_url = "https://localhost:8282"
    timeout = 30

    try:
        logger.info(f"正在连接服务器 {server_url}...")
        response = requests.get(f"{server_url}/openavatarchat/initconfig", verify=False, timeout=timeout)
        if response.status_code == 200:
            config = response.json()
            logger.info("获取配置成功")
            rtc_config_data = config.get('rtc_configuration', {})
            logger.info(f"原始RTC配置: {rtc_config_data}")
        else:
            logger.exception(f"获取配置失败: {response.status_code}")
            return
    except requests.exceptions.ConnectionError:
        logger.exception(f"无法连接到服务器 {server_url}，请确保服务已启动")
        logger.exception("检查服务是否运行在正确端口")
        return
    except requests.exceptions.Timeout:
        logger.exception(f"连接服务器超时，请检查网络")
        return
    except Exception as e:
        logger.exception("连接服务失败")
        return

    try:
        rtc_config = RTCConfiguration()
        rtc_config.iceServers = []
        rtc_config.certificates = []
        logger.info("使用空配置（无证书）的RTCPeerConnection")
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
                logger.exception(f"发送ICE候选失败: {response.status_code}")
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
        offer = await asyncio.wait_for(pc.createOffer(), timeout=30)
        logger.info("创建offer成功")
    except asyncio.TimeoutError:
        logger.exception("创建offer超时")
        await pc.close()
        return
    except Exception as e:
        logger.exception("创建offer失败")
        await pc.close()
        return

    try:
        await asyncio.wait_for(pc.setLocalDescription(offer), timeout=30)
        logger.info("设置本地描述成功")
    except asyncio.TimeoutError:
        logger.exception("设置本地描述超时")
        await pc.close()
        return
    except Exception as e:
        logger.exception("设置本地描述失败")
        await pc.close()
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
            logger.info(f"Answer SDP长度: {len(answer.get('sdp', ''))}")
            logger.info(f"Answer type: {answer.get('type', '')}")

            await asyncio.wait_for(pc.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type=answer['type'])), timeout=30)
            logger.info("设置远程描述成功")
        else:
            logger.exception(f"发送offer失败: {response.status_code}")
            logger.exception(f"响应内容: {response.text}")
            await pc.close()
            return
    except requests.exceptions.Timeout:
        logger.exception("发送offer超时，请检查服务是否正常运行")
        await pc.close()
        return
    except asyncio.TimeoutError:
        logger.exception("设置远程描述超时")
        await pc.close()
        return
    except Exception as e:
        logger.exception("发送offer异常")
        await pc.close()
        return

    logger.info("等待ICE连接建立（3秒）...")
    try:
        await asyncio.sleep(3)
    except Exception as e:
        logger.exception("等待异常")

    logger.info(f"ICE连接状态: {pc.iceConnectionState}")
    logger.info(f"Data Channel状态: {data_channel.readyState}")

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

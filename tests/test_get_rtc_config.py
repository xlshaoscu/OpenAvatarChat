import requests
import urllib3
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

server_url = "https://localhost:8282"
timeout = 30

logger.info("正在获取服务端配置...")

try:
    response = requests.get(f"{server_url}/openavatarchat/initconfig", verify=False, timeout=timeout)
    if response.status_code == 200:
        config = response.json()
        logger.info("获取配置成功!")

        rtc_config = config.get('rtc_configuration', {})
        logger.info(f"原始RTC配置: {json.dumps(rtc_config, indent=2)}")

        logger.info("配置详情:")
        if 'iceServers' in rtc_config:
            logger.info(f"ICE Servers 数量: {len(rtc_config.get('iceServers', []))}")
            for i, server in enumerate(rtc_config.get('iceServers', [])):
                logger.info(f"ICE Server {i+1}: urls={server.get('urls', 'N/A')}, username={server.get('username', 'N/A')}, credential={server.get('credential', 'N/A')}")
        else:
            logger.info("iceServers: 未配置")

        logger.info(f"完整配置: {json.dumps(config, indent=2, ensure_ascii=False)}")

    else:
        logger.error(f"获取配置失败: {response.status_code}, 响应内容: {response.text}")

except requests.exceptions.ConnectionError as e:
    logger.error(f"无法连接到服务器 {server_url}, 请确保服务已启动")
except requests.exceptions.Timeout as e:
    logger.error(f"连接超时: {e}")
except Exception as e:
    logger.exception(f"错误: {e}")

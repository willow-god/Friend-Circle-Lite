"""统一网页请求封装。

本模块负责把“直连优先，失败后自动尝试代理”的请求逻辑收口到一个地方。
调用方只关心是否拿到响应，不需要感知重试细节。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from friend_circle_lite.config.models import ProxySettings
from friend_circle_lite.domain.models import normalize_latency


@dataclass(slots=True)
class FetchResult:
    """一次网页请求的结果。"""

    response: requests.Response | None
    latency: float = -1
    used_proxy: bool = False

    @property
    def success(self) -> bool:
        """是否成功取得 HTTP 200 响应。"""
        return self.response is not None and self.response.status_code == 200


class WebFetchClient:
    """网页请求客户端，封装直连和代理回退逻辑。"""

    def __init__(self, session: requests.Session, proxy_settings: ProxySettings | None = None):
        self.session = session
        self.proxy_settings = proxy_settings or ProxySettings()

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int | tuple | None = None,
        desc: str = "网页请求",
    ) -> FetchResult:
        """先直连请求，失败时自动尝试代理请求。"""
        direct = self._get_once(url, headers=headers, timeout=timeout, desc=desc, used_proxy=False)
        if direct.success or not self.proxy_settings.proxy_url:
            return direct

        proxy_url = self._build_proxy_url(url)
        proxy = self._get_once(
            proxy_url,
            headers=headers,
            timeout=timeout,
            desc=f"{desc} 代理",
            used_proxy=True,
            display_url=f"{url} （通过代理）",
        )
        return proxy if proxy.success else direct

    def _get_once(
        self,
        url: str,
        headers: dict[str, str] | None,
        timeout: int | tuple | None,
        desc: str,
        used_proxy: bool,
        display_url: str | None = None,
    ) -> FetchResult:
        log_url = display_url or url
        start_time = time.time()
        try:
            response = self.session.get(url, headers=headers, timeout=timeout)
            latency = self._elapsed_latency(start_time)
            if response.status_code == 200:
                logging.info(f"[{desc}] 成功访问: {log_url} ，延迟 {latency} 秒")
            else:
                logging.warning(f"[{desc}] 状态码异常: {log_url} -> {response.status_code}")
            return FetchResult(response=response, latency=latency, used_proxy=used_proxy)
        except requests.RequestException as exc:
            error_text = exc.__class__.__name__ if used_proxy else str(exc)
            logging.warning(f"[{desc}] 请求失败: {log_url} ，错误: {error_text}")
            return FetchResult(response=None, latency=self._elapsed_latency(start_time), used_proxy=used_proxy)

    def _build_proxy_url(self, url: str) -> str:
        proxy_url = self.proxy_settings.proxy_url
        if "{}" in proxy_url:
            return proxy_url.format(url)
        if "{url}" in proxy_url:
            return proxy_url.format(url=url)
        return f"{proxy_url}{url}"

    @staticmethod
    def _elapsed_latency(start_time: float) -> float:
        return normalize_latency(time.time() - start_time)

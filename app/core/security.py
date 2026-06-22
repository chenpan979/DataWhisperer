from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """生成密码哈希。

    当前阶段使用 Python 标准库 `pbkdf2_hmac`，避免为了演示项目额外引入依赖。
    真实生产环境可以替换为 Argon2、bcrypt 或统一账号中心。
    """

    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            salt,
            _b64encode(digest),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码。

    V3.13.1 的 demo 种子用户还没有真实哈希，这里兼容一次历史占位值，
    让 `demo / admin / 12345678` 可以平滑登录，登录成功后会升级为真实哈希。
    """

    if password_hash == "demo-password-hash-placeholder":
        return password == "12345678"

    try:
        algorithm, iterations_text, salt, expected_text = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_text),
        )
        expected = _b64decode(expected_text)
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def password_hash_needs_upgrade(password_hash: str) -> bool:
    """判断密码哈希是否需要升级。"""

    if password_hash == "demo-password-hash-placeholder":
        return True
    try:
        algorithm, iterations_text, *_ = password_hash.split("$", 3)
        return algorithm != PASSWORD_ALGORITHM or int(iterations_text) < PASSWORD_ITERATIONS
    except (ValueError, TypeError):
        return True


def create_signed_token(payload: dict[str, Any], *, secret: str, expires_in: int) -> str:
    """创建 HMAC 签名访问令牌。"""

    now = int(time.time())
    token_payload = {
        **payload,
        "iat": now,
        "exp": now + expires_in,
    }
    body = _b64encode(json.dumps(token_payload, ensure_ascii=False, separators=(",", ":")).encode())
    signature = _sign(body, secret)
    return f"{body}.{signature}"


def parse_signed_token(token: str, *, secret: str) -> dict[str, Any]:
    """解析并校验访问令牌。"""

    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("无效的登录凭证。") from exc

    expected_signature = _sign(body, secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("登录凭证签名无效。")

    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("登录凭证内容无效。") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("登录状态已过期，请重新登录。")
    return payload


def _sign(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8"))

import logging
import smtplib
import socket
import time
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr
from jinja2 import Environment, FileSystemLoader

# ============================================================
# 内部工具
# ============================================================

def _render_message(
    target_email,
    sender_email,
    subject,
    body,
    template_path=None,
    template_data=None,
):
    """
    构建 MIME 邮件对象，支持纯文本 + 可选 HTML。
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = target_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = sender_email.split("@")[-1] if "@" in sender_email else "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)

    # 纯文本内容
    msg.attach(MIMEText(body or "", "plain", "utf-8"))

    # HTML 模板内容
    if template_path and template_data:
        env = Environment(loader=FileSystemLoader(os.path.dirname(template_path)))
        template = env.get_template(os.path.basename(template_path))
        html_content = template.render(template_data)
        msg.attach(MIMEText(html_content, "html", "utf-8"))

    return msg


def _smtp_connect(smtp_server, port, sender_email, password, use_tls=True, timeout=30):
    """
    智能 SMTP 连接：
    - use_tls=True: 优先尝试 SMTP_SSL，失败则回退到 SMTP + STARTTLS。
    - use_tls=False: 明文连接。
    """
    try:
        if use_tls:
            try:
                server = smtplib.SMTP_SSL(smtp_server, port, timeout=timeout)
            except Exception as e_ssl:
                logging.warning(f"SMTP_SSL 连接失败，尝试 STARTTLS: {e_ssl}")
                server = smtplib.SMTP(smtp_server, port, timeout=timeout)
                server.starttls()
        else:
            server = smtplib.SMTP(smtp_server, port, timeout=timeout)

        server.login(sender_email, password)
        return server
    except Exception as e:
        logging.error(f"SMTP 连接失败: {e}")
        raise


def _validate_email(addr: str) -> bool:
    """
    基础 email 格式检查。
    """
    if not addr:
        return False
    name, email = parseaddr(addr)
    if "@" not in email or email.count("@") != 1:
        return False
    local, domain = email.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return False
    return True


# ============================================================
# 单封邮件发送
# ============================================================

def email_sender(
    target_email,
    sender_email,
    smtp_server,
    port,
    password,
    subject,
    body,
    template_path=None,
    template_data=None,
    use_tls=True,
):
    """
    发送单封邮件。
    """
    msg = _render_message(
        target_email=target_email,
        sender_email=sender_email,
        subject=subject,
        body=body,
        template_path=template_path,
        template_data=template_data,
    )

    try:
        server = _smtp_connect(smtp_server, port, sender_email, password, use_tls=use_tls)
        server.sendmail(sender_email, [target_email], msg.as_string())
        server.quit()
        print(f"邮件已发送到 {target_email}")
    except Exception as e:
        logging.error(f"邮件发送失败，目标地址: {target_email}，错误信息: {e}")


# ============================================================
# 批量邮件发送
# ============================================================

def send_emails(
    emails,
    sender_email,
    smtp_server,
    port,
    password,
    subject,
    body,
    template_path=None,
    template_data=None,
    use_tls=True,
):
    """
    批量发送邮件：
    - 分批（默认100封为一批，可通过 EMAIL_BATCH_SIZE 环境变量调整）
    - 单封发送，防止泄露邮箱
    - SMTP 连接复用，失败隔离
    - 返回 summary
    """
    batch_size = int(os.getenv("EMAIL_BATCH_SIZE", "100"))
    sleep_between_batches = float(os.getenv("EMAIL_BATCH_SLEEP", "0"))
    validate_strict = os.getenv("EMAIL_VALIDATE_STRICT", "1") not in ("0", "false", "False")

    # 去重 & 校验
    seen = set()
    cleaned, invalid = [], []
    for addr in emails:
        addr = addr.strip()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        if validate_strict and not _validate_email(addr):
            invalid.append(addr)
            logging.warning(f"无效邮箱: {addr}")
            continue
        cleaned.append(addr)

    total = len(cleaned)
    logging.info(f"准备发送 {total} 封邮件 (原始 {len(emails)}, 无效 {len(invalid)})")

    if total == 0:
        return {
            "total_requested": len(emails),
            "total_valid": 0,
            "sent_success": 0,
            "sent_failed": 0,
            "invalid": invalid,
            "failed": [],
        }

    # 预渲染 HTML 模板
    html_cache = None
    if template_path and template_data:
        env = Environment(loader=FileSystemLoader(os.path.dirname(template_path)))
        template = env.get_template(os.path.basename(template_path))
        html_cache = template.render(template_data)

    def build_msg_for(to_addr):
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        domain = sender_email.split("@")[-1] if "@" in sender_email else "localhost"
        msg["Message-ID"] = make_msgid(domain=domain)
        msg.attach(MIMEText(body or "", "plain", "utf-8"))
        if html_cache:
            msg.attach(MIMEText(html_cache, "html", "utf-8"))
        return msg

    try:
        server = _smtp_connect(smtp_server, port, sender_email, password, use_tls=use_tls)
    except Exception:
        return {
            "total_requested": len(emails),
            "total_valid": total,
            "sent_success": 0,
            "sent_failed": total,
            "invalid": invalid,
            "failed": cleaned,
        }

    successes, failures = [], []

    for i in range(0, total, batch_size):
        batch = cleaned[i:i + batch_size]
        logging.info(f"发送批次 {i // batch_size + 1}: {len(batch)} 封")

        for addr in batch:
            msg = build_msg_for(addr)
            try:
                refused = server.sendmail(sender_email, [addr], msg.as_string())
                if refused:
                    failures.append(addr)
                    logging.error(f"发送被拒绝: {addr} - {refused}")
                else:
                    successes.append(addr)
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError):
                # 尝试重连一次
                try:
                    logging.warning("SMTP 连接断开，尝试重连...")
                    server = _smtp_connect(smtp_server, port, sender_email, password, use_tls=use_tls)
                    server.sendmail(sender_email, [addr], msg.as_string())
                    successes.append(addr)
                except Exception as e:
                    failures.append(addr)
                    logging.error(f"重连后发送失败: {addr} - {e}")
            except Exception as e:
                failures.append(addr)
                logging.error(f"发送失败: {addr} - {e}")

        if sleep_between_batches > 0 and i + batch_size < total:
            time.sleep(sleep_between_batches)

    try:
        server.quit()
    except Exception:
        pass

    summary = {
        "total_requested": len(emails),
        "total_valid": total,
        "sent_success": len(successes),
        "sent_failed": len(failures),
        "invalid": invalid,
        "success": successes,
        "failed": failures,
    }
    logging.info(f"批量发送完成: 成功 {summary['sent_success']} / {summary['total_valid']}")
    return summary

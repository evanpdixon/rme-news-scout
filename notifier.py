"""
Push Notification via ntfy.sh
Sends a notification with a "View Report" button linking to the
GitHub Pages hosted report.
"""

import os
import httpx


def send_notification(
    topic: str,
    title: str,
    message: str,
    html_path: str = "",
    report_url: str = "",
    server: str = "https://ntfy.sh",
) -> bool:
    """Send a push notification with an optional link to the hosted report.

    Args:
        topic: The ntfy topic to publish to (e.g. 'rme-news-scout').
        title: Notification title.
        message: Notification body text.
        html_path: Unused, kept for backward compatibility.
        report_url: URL to the hosted HTML report.
        server: ntfy server URL (default: public ntfy.sh).

    Returns:
        True if sent successfully.
    """
    url = f"{server}/{topic}"

    try:
        headers = {
            "Title": title,
            "Tags": "newspaper,radio",
        }
        if report_url:
            headers["Actions"] = f"view, View Report, {report_url}, clear=true"

        resp = httpx.post(url, content=message, headers=headers, timeout=10)
        resp.raise_for_status()

        print(f"  [Notify] Push notification sent to topic '{topic}'")
        if report_url:
            print(f"  [Notify] Report URL: {report_url}")
        return True

    except Exception as e:
        print(f"  [Notify] Failed to send notification: {e}")
        return False

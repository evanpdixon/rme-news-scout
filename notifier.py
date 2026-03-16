"""
Push Notification via ntfy.sh
Uploads the HTML report and sends a notification with a "View Report"
button that opens it directly in the phone's browser.
No account or API key needed.
"""

import json
import os
import httpx


def send_notification(
    topic: str,
    title: str,
    message: str,
    html_path: str = "",
    server: str = "https://ntfy.sh",
) -> bool:
    """Upload the HTML report to ntfy, then send a notification with a link.

    Args:
        topic: The ntfy topic to publish to (e.g. 'rme-news-scout').
        title: Notification title.
        message: Notification body text.
        html_path: Path to the HTML report file to upload.
        server: ntfy server URL (default: public ntfy.sh).

    Returns:
        True if sent successfully.
    """
    url = f"{server}/{topic}"

    try:
        report_url = ""

        # Step 1: Upload the HTML file to get a hosted URL
        if html_path and os.path.exists(html_path):
            filename = os.path.basename(html_path)
            with open(html_path, "rb") as f:
                upload_resp = httpx.put(
                    url,
                    content=f.read(),
                    headers={
                        "Title": "Report uploaded",
                        "Filename": filename,
                        "Message": "Uploading report...",
                        "Priority": "1",  # min priority so this doesn't buzz
                    },
                    timeout=30,
                )
            upload_resp.raise_for_status()
            data = json.loads(upload_resp.text)
            report_url = data.get("attachment", {}).get("url", "")

        # Step 2: Send the actual notification with a View Report button
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

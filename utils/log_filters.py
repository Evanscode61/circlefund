import logging
import re


class RedactInvitationToken(logging.Filter):
    path = re.compile(r"(/api/v1/invitations/)[^/?\s]+(/(?:accept|reject)\b)")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.path.sub(r"\1[redacted]\2", message)
        if message != redacted:
            record.msg = redacted
            record.args = ()
        return True

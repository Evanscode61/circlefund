from config.celery import app


@app.task(ignore_result=True)
def deliver_password_reset_otp(*, email: str) -> None:
    # AccountService imports this task to enqueue it.
    from accounts.services import AccountService

    AccountService.deliver_password_reset_otp(email=email)

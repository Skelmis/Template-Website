import datetime
import os

import saq
from dotenv import load_dotenv
from saq import CronJob, Queue
from saq.types import SettingsDict

from template import constants

load_dotenv()


async def tick(_):
    print(f"tick {datetime.datetime.now(datetime.timezone.utc)}")


async def before_process(ctx):
    print(f"Starting job: {ctx['job'].function}\n\tWith kwargs: {ctx['job'].kwargs}")
    job: saq.Job = ctx["job"]
    job.retries = 0
    job.timeout = SAQ_TIMEOUT


async def after_process(ctx):
    print(f"Finished job: {ctx['job'].function}\n\tWith kwargs: {ctx['job'].kwargs}")


async def startup(_):
    # Ensure logger is started in SAQ process
    constants.configure_otel()


SAQ_TIMEOUT = int(datetime.timedelta(hours=1).total_seconds())
SAQ_QUEUE = Queue.from_url(os.environ.get("REDIS_URL"))

SAQ_SETTINGS = SettingsDict(
    queue=SAQ_QUEUE,
    functions=[
        tick,
    ],
    concurrency=10,
    startup=startup,
    before_process=before_process,
    after_process=after_process,
    # https://crontab.guru
    cron_jobs=[
        # run every 30 seconds
        # CronJob(tick, cron="* * * * * */30"),
        # Once per day, at the top of the day
        CronJob(
            tick,
            cron="0 0 * * */1",
            timeout=SAQ_TIMEOUT,
            retries=1,
        ),
    ],
)

"""Check RTL reindex progress: Lambda invocations + OpenSearch indexed count."""
import boto3
import sys
from datetime import datetime, timedelta, timezone

REGION = "ap-northeast-2"
LOG_GROUP = "/aws/lambda/lambda-rtl-parser-seoul-dev"
LAMBDA_NAME = "lambda-rtl-parser-seoul-dev"

logs = boto3.client("logs", region_name=REGION)
cw = boto3.client("cloudwatch", region_name=REGION)


def lambda_metric(metric_name, minutes=2, stat="Sum"):
    """Get Lambda CloudWatch metric over last N minutes."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    resp = cw.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName=metric_name,
        Dimensions=[{"Name": "FunctionName", "Value": LAMBDA_NAME}],
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=[stat],
    )
    points = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
    return [(p["Timestamp"].strftime("%H:%M"), p.get(stat, 0)) for p in points]


if __name__ == "__main__":
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(f"=== Lambda metrics last {minutes} min ===")
    for name, stat in [
        ("Invocations", "Sum"),
        ("Errors", "Sum"),
        ("ConcurrentExecutions", "Maximum"),
        ("Throttles", "Sum"),
        ("Duration", "Average"),
    ]:
        points = lambda_metric(name, minutes, stat)
        if not points:
            print(f"  {name:22s}: (no data)")
            continue
        total = sum(v for _, v in points)
        per_min = " ".join(f"{ts}={int(v)}" for ts, v in points[-5:])
        unit = " ms" if name == "Duration" else ""
        print(f"  {name:22s}: total={int(total)}{unit}  per-min=[{per_min}]")

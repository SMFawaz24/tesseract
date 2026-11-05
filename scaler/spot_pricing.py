"""
spot_pricing.py - Live AWS EC2 Spot Market Price Reader.
Queries AWS EC2 DescribeSpotPriceHistory API to dynamically obtain
real-time market prices for instance types in the current region.
"""
import boto3
from datetime import datetime, timezone, timedelta

class SpotPriceReader:
    def __init__(self, region="us-east-1", instance_type="t3.small", product_desc="Linux/UNIX"):
        self.region = region
        self.instance_type = instance_type
        self.product_desc = product_desc
        self.ec2 = boto3.client("ec2", region_name=region)
        self.cached_price = 0.0062  # Typical t3.small spot baseline (~$0.0062/hr vs $0.0208 on-demand)
        self.last_fetch = None

    def get_live_spot_price(self) -> dict:
        """
        Fetches the latest spot price from AWS EC2 API.
        Returns:
            dict containing spot_price, on_demand_price, savings_percent, and timestamp.
        """
        on_demand_price = 0.0208  # AWS list price for t3.small in us-east-1
        now = datetime.now(timezone.utc)

        try:
            # Query last 1 hour of spot price history
            start_time = now - timedelta(hours=1)
            response = self.ec2.describe_spot_price_history(
                InstanceTypes=[self.instance_type],
                ProductDescriptions=[self.product_desc],
                StartTime=start_time,
                EndTime=now,
                MaxResults=5
            )

            history = response.get("SpotPriceHistory", [])
            if history:
                # Latest price entry
                latest = history[0]
                price = float(latest["SpotPrice"])
                az = latest.get("AvailabilityZone", "us-east-1a")
                self.cached_price = price
                savings = ((on_demand_price - price) / on_demand_price) * 100.0
                return {
                    "spot_price_per_hour": round(price, 5),
                    "on_demand_price_per_hour": on_demand_price,
                    "savings_percent": round(savings, 1),
                    "availability_zone": az,
                    "source": "live_aws_api"
                }
        except Exception as e:
            # Graceful fallback if offline or lab policy blocks DescribeSpotPriceHistory
            pass

        # Return cached / realistic baseline
        savings = ((on_demand_price - self.cached_price) / on_demand_price) * 100.0
        return {
            "spot_price_per_hour": round(self.cached_price, 5),
            "on_demand_price_per_hour": on_demand_price,
            "savings_percent": round(savings, 1),
            "availability_zone": f"{self.region}a",
            "source": "cached_estimate"
        }


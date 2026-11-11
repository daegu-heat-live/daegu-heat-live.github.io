"""저장소가 계속 커지지 않도록 3일보다 오래된 실황·예보 아카이브를 지운다(배포용)."""
from datetime import datetime, timedelta

from scripts.common import ROOT
from scripts.live.kma_time import KST


def main(days: int = 3):
    cut = (datetime.now(KST) - timedelta(days=days)).strftime("%Y%m%d")
    n = 0
    for kind in ("nowcast", "forecast"):
        for p in (ROOT / "data" / "live" / kind).glob("*.json"):
            if p.stem[:8] < cut:
                p.unlink()
                n += 1
    print("pruned", n)


if __name__ == "__main__":
    main()

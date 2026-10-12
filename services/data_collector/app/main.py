from shared.utils.logging import configure_logging

from .adapters import BinanceAdapter, BybitAdapter, OKXAdapter
from .collectors import RestMarketDataCollector


def create_adapters() -> tuple[BinanceAdapter, BybitAdapter, OKXAdapter]:
    return BinanceAdapter(), BybitAdapter(), OKXAdapter()


def main() -> None:
    configure_logging()
    RestMarketDataCollector()
    print("Data collector service ready")


if __name__ == "__main__":
    main()

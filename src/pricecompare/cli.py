from __future__ import annotations

import argparse
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .collectors import aiz, darwish, action, opencart, pages, platinum, shopify, stores, woocommerce
from .collectors.base import PoliteClient
from .db.models import CollectionRun, Source
from .db.session import get_engine, init_db, make_session
from . import report
from .matching import matcher
from .store import ensure_store, save_offers

# slug -> name, base url, method, terms rating, params. Handles/URLs confirmed in dry runs.
# Each shop lists its phone section, its tablet section (2026-11-11) and its laptop section (2026-11-12, Stage 3:
# robots.txt of every laptop address checked that day); Platinum and Darwish are read from their sitemaps.
# City Center and Action laptops are not read: their titles almost never give the exact processor.
SOURCES = {
    "smartbuy": ("SmartBuy", "https://smartbuy-me.com", "shopify_json", "unknown", {"handles": ["mobile-phone", "apple-watches", "smart-watch", "tablets", "laptops", "notebooks", "gaming-notebook", "macbook", "mac-book", "tvs", "qled-tvs"]}),
    "igeek": ("iGeek Megastore", "https://igeekjo.com", "shopify_json", "green", {"handles": ["mobile-phones", "laptops-1"]}),  # added 2026-11-12
    "estorejo": ("eStoreJO", "https://estorejo.com", "shopify_json", "amber", {"handles": ["iphone", "ipad", "macbook-air", "macbook-pro", "macbook-neo", "apple-watch"]}),
    "iservice": ("iService", "https://iservicejo.com", "woocommerce_html", "green", {"listings": [
        f"https://iservicejo.com/store/mobile-phones/{b}/"
        for b in ("iphone", "samsung", "xiaomi", "honor", "infinix", "tecno", "realme")] + ["https://iservicejo.com/store/apple-watch/"]
        + ["https://iservicejo.com/store/tablets/", "https://iservicejo.com/store/laptops/"]}),
    "leaders": ("Leaders Center", "https://leaders.jo", "woocommerce_html", "green", {"listings": [
        "https://leaders.jo/en/product-category/all-products/electronics/mobiles/mobile-devices/",
        "https://leaders.jo/en/product-category/all-products/electronics/tablets-and-accessories/tablets/",
        "https://leaders.jo/en/product-category/all-products/electronics/laptops/",
        "https://leaders.jo/en/product-category/all-products/home-appliance/tv-and-video-screens/tv-screens/"]}),
    "alaryan": ("Al-Aryan Mobile", "https://alaryanmobile.com", "woocommerce_html", "green", {"listings": [
        "https://alaryanmobile.com/product-category/smart-watches-bands/smart-watches/",
        "https://alaryanmobile.com/product-category/mobile-phones/",
        "https://alaryanmobile.com/product-category/laptops-tablets/tablets/",
        "https://alaryanmobile.com/product-category/laptops-tablets/mac/"]}),
    "ammar": ("Ammar Mobile", "https://ammarmobile.com", "opencart_html", "green", {"listings": [
        "https://ammarmobile.com/en-gb/category/mobile-phones-smartphones-latest-devices",
        "https://ammarmobile.com/en-gb/category/AMMAR-TABLETS-CATEGORY",
        "https://ammarmobile.com/en-gb/category/laptops-gaming-business-student-everyday-jordan"]}),
    "gts": ("GTS", "https://gts.jo", "opencart_html", "amber", {"listings": ["https://gts.jo/phone-tablets/mobile", "https://gts.jo/phone-tablets/smart-watch", "https://gts.jo/phone-tablets/tablets", "https://gts.jo/computers/laptops", "https://gts.jo/tvs-projectors/tvs"]}),
    "citycenter": ("City Center", "https://citycenter.jo", "opencart_html", "green", {"listings": [
        "https://citycenter.jo/electronics/electronics-smartphone",
        "https://citycenter.jo/pc-and-laptops/pc-and-laptops-tablet-pc"]}),
    "action": ("Action", "https://action.jo", "nuxt_html", "amber", {"listings": ["https://action.jo/en/category/smartphones", "https://action.jo/en/category/tablets"]}),
    "platinum": ("Platinum", "https://www.platinum-jo.com", "sitemap_pages", "green", {}),
    # added 2026-11-13 (robots.txt allows our reader; terms read, no rule against automated reading; see data-source-permissions)
    "xmart": ("Xmart", "https://www.xmart.jo/en", "shopify_json", "green", {"handles": ["smartphones", "tablets", "laptops", "tvs", "smart-watches"]}),
    "dna": ("DNA Jordan", "https://dna.jo", "shopify_json", "green",
            {"handles": ["apple-iphone", "mobility-phones", "apple-ipad", "tech-tablets", "tech-laptop"]}),
    # added 2026-11-19 (owner: "search for new shops"; robots.txt allows, terms have no rule against automated reading)
    "bci": ("BCI Online Store", "https://jo.bcitechstore.com", "woocommerce_html", "green", {"listings": [
        "https://jo.bcitechstore.com/product-category/smartphones/",
        "https://jo.bcitechstore.com/product-category/mobile/tablets/",
        "https://jo.bcitechstore.com/product-category/wearables-2/smart-watches/",
        "https://jo.bcitechstore.com/product-category/xiaomi-tvs/"]}),
    "numberone": ("Number One Store", "https://numberonestore.net", "opencart_html", "green", {"listings": [
        "https://numberonestore.net/components/monitors/gaming-monitor",
        "https://numberonestore.net/components/monitors/office-monitor",
        "https://numberonestore.net/video-games/Playstation/playstation-5",
        "https://numberonestore.net/video-games/xbox-microsoft/xbox-console",
        "https://numberonestore.net/video-games/nintendo-Switch/nintendo-switch-console"]}),
    "newvision": ("New Vision", "https://newvision.jo", "woocommerce_html", "green",
                  {"listings": ["https://newvision.jo/en/product-category/tvs/"]}),
    # Baghdad Corner / ركن بغداد (2026-11-23, owner): terms forbid copying texts and pictures, nothing on reading prices;
    # robots.txt allows the category pages. Price, name and link only (collectors/aiz.py)
    "rokon": ("Baghdad Corner", "https://rokonbaghdad-jo.com", "aiz_html", "amber", {"listings": [
        "https://rokonbaghdad-jo.com/en/category/mobile-phones", "https://rokonbaghdad-jo.com/en/category/tablets",
        "https://rokonbaghdad-jo.com/en/category/laptops", "https://rokonbaghdad-jo.com/en/category/screen-tvs"]}),
    "compujordan": ("Compu Jordan", "https://compujordan.com", "opencart_html", "green", {"listings": [
        "https://compujordan.com/electronics/smart-watches",
        "https://compujordan.com/pc-and-laptops/laptops", "https://compujordan.com/pc-and-laptops/tablets",
        "https://compujordan.com/monitor-and-display/tv"]}),
    # added 2026-11-14 from a Jordan store directory; robots.txt allows, no rule against automated reading in the terms
    "osjo": ("Oriental Store", "https://os-jo.com", "opencart_html", "green", {"listings": [
        "https://os-jo.com/computer-systems/laptops", "https://os-jo.com/gaming-in-jordan/gaming-laptop"]}),
    "smartsystems": ("Smart Systems", "https://smartsystems.jo", "opencart_html", "green", {"listings": [
        "https://smartsystems.jo/computer-systems/laptop-and-tablet-pcs-computer-systems/laptops-laptop-and-tablet-pcs",
        "https://smartsystems.jo/computer-systems/laptop-and-tablet-pcs-computer-systems/tablet-android-laptop-and-tablet-pcs",
        "https://smartsystems.jo/computer-systems/laptop-and-tablet-pcs-computer-systems/tablet-pc-laptop-and-tablet-pcs"]}),
    "midteks": ("Midteks", "https://midteks.com", "opencart_html", "green", {"listings": [
        "https://midteks.com/computer-systems/laptops", "https://midteks.com/gaming/laptops-1",
        "https://midteks.com/computer-systems/tablet", "https://midteks.com/electronics/mobile/mobile-device"]}),
    "cse": ("CSE Jordan", "https://cse.jo", "opencart_html", "green", {"listings": ["https://cse.jo/computer-systems/laptop"]}),
    "almohanad": ("Al-Mohanad Tech", "https://almohanadtech.com", "woocommerce_html", "green", {"listings": [
        "https://almohanadtech.com/product-category/laptops/", "https://almohanadtech.com/product-category/apple-tablets/"]}),
    "pccircle": ("PC Circle", "https://pccircle.com", "woocommerce_html", "green",
                 {"listings": ["https://pccircle.com/product-category/laptops-notebooks/"]}),
    "h4m": ("Hawaii Telecom", "https://h4mjo.com", "woocommerce_html", "green",
            {"listings": ["https://h4mjo.com/smart-phone/", "https://h4mjo.com/tablets/", "https://h4mjo.com/smart-watch/"]}),
    "newton": ("Newton Stores", "https://newtonstores.com", "odoo_html", "green", {"listings": [
        "https://newtonstores.com/shop/category/tvs-home-theatres-tvs-40"]}),
    "profpc": ("The Professional PC", "https://www.theprofpc.com", "site123_html", "green", {"listings": [
        "https://www.theprofpc.com/shop/laptops", "https://www.theprofpc.com/shop/mobiles-and-tablet"]}),
    "alruwwad": ("Al-Ruwwad", "https://al-ruwwad.com", "zoho_html", "green", {"listings": [
        "https://al-ruwwad.com/categories/smart-tv/6640546000000143098", "https://al-ruwwad.com/categories/normal-tv/6640546000000143120"]}),
    # Magento; home page is behind a bot challenge (never fetched), sitemap and product pages are open. Owner asked for it 2026-11-12.
    "darwish": ("Darwish Electronics", "https://darwishelectronics.jo", "darwish_sitemap", "amber", {}),
}
CATALOG_CSV = Path(__file__).resolve().parents[2] / "data" / "catalog.csv"


# Stage 3 electronics sections (2026-11-14): read in their own run (collect --part electronics, every 6 hours) so the hourly
# run stays short. Picked from the section survey (scripts/section_survey.py); robots.txt checked on every fetch as always.
# City Center: since 2026-11-27 its sections are in ELECTRONICS_MORE_SECTIONS (signed; a refusal rests only those).
ELECTRONICS = {
    "numberone": ["https://numberonestore.net/audio/headset", "https://numberonestore.net/audio/earphone",
                  "https://numberonestore.net/audio/speakers", "https://numberonestore.net/components/storage",
                  "https://numberonestore.net/network-and-adapter/network-devices"],
    "bci": ["https://jo.bcitechstore.com/product-category/mobile/tws-earphones/",
            "https://jo.bcitechstore.com/product-category/mobile/charging/power-banks/",
            "https://jo.bcitechstore.com/product-category/office-tools/office-essentials/Monitors/",
            "https://jo.bcitechstore.com/product-category/office-tools/office-essentials/routers/",
            "https://jo.bcitechstore.com/product-category/xiaomi/xiaomi-audiohubs-speakers/"],
    "smartbuy": ["headphones", "speakers", "sound-bar", "gaming-consoles", "monitors", "gaming-monitors", "printers", "imac", "routers", "storage", "cameras", "digital-cameras", "instant-cameras"],
    "xmart": ["headphones-earbuds", "bluetooth-speakers", "home-audio-systems", "storage-devices", "desktop", "gopro"],
    "igeek": ["earbuds-earphones", "headsets", "monitors", "nintendo-switch-2-console", "nintendo-switch-console", "xbox-console", "playstation-5-collection", "network", "power-bank", "internal-storage", "external-storage", "printers"],
    "estorejo": ["airpods", "audio", "imac", "mac-mini", "power-banks"],
    "dna": ["audio-earphones", "audio-headphones", "apple-airpods-audio", "gaming-consoles", "tech-monitors", "accessories-power-banks", "cameras", "tech-routers", "apple-imac"],
    "iservice": [
        "https://iservicejo.com/store/accessories/headphones/",
        "https://iservicejo.com/store/accessories/speakers/",
        "https://iservicejo.com/store/accessories/power-banks/",
        "https://iservicejo.com/store/gaming/",
    ],
    "alaryan": [
        "https://alaryanmobile.com/product-category/audio",
        "https://alaryanmobile.com/product-category/network/",
        "https://alaryanmobile.com/product-category/accessories/power-banks/",
        "https://alaryanmobile.com/product-category/security-smart-home/smart-cameras/",
        "https://alaryanmobile.com/product-category/gaming/",      # PS5 consoles (2026-11-25)
    ],
    "ammar": [
        "https://ammarmobile.com/en-gb/category/computer-monitors-gaming-office-led-ips-full-hd-4k-display",
        "https://ammarmobile.com/en-gb/category/printers-ink-toner-home-office-printing-jordan/printers-inkjet-laser-wireless-office-home-jordan",
        "https://ammarmobile.com/en-gb/category/desktop-pcs-custom-gaming-computers-jordan/branded-desktop-pcs-dell-hp-lenovo-jordan",
    ],
    "gts": [
        "https://gts.jo/audio",
        "https://gts.jo/accessories/phone-accessories/handsfree-earphone",
        "https://gts.jo/computers/monitor",
        "https://gts.jo/gaming/gaming-monitor",
        "https://gts.jo/printers-supplies-1",
        "https://gts.jo/accessories/phone-accessories/power-bank",
        "https://gts.jo/components/external-storage",
        "https://gts.jo/cameras",
    ],
    "compujordan": [
        "https://compujordan.com/computer-hardware/audio",
        "https://compujordan.com/gaming-rampage/gaming-accessories/gaming-headsets",
        "https://compujordan.com/monitor-and-display",
        "https://compujordan.com/gaming-rampage/gaming-monitor",
        "https://compujordan.com/printers-and-scanners",
        "https://compujordan.com/pc-and-laptops/all-in-one",
        "https://compujordan.com/pc-and-laptops/desktops",
        "https://compujordan.com/computer-hardware/networking",
        "https://compujordan.com/electronics/power-bank",
        "https://compujordan.com/computer-hardware/storage",
    ],
    "osjo": [
        "https://os-jo.com/accessories/audio",
        "https://os-jo.com/components/computer-monitors",
        "https://os-jo.com/printers-scanners",
        "https://os-jo.com/computer-systems/desktop-computer",
        "https://os-jo.com/gaming-in-jordan/gaming-desktop",
        "https://os-jo.com/network",
        "https://os-jo.com/accessories/power-banks",
        "https://os-jo.com/components/storage",
    ],
    "smartsystems": [
        "https://smartsystems.jo/computer-systems/monitors-and-projectors-computer-systems",
        "https://smartsystems.jo/printers-and-scanners",
        "https://smartsystems.jo/computer-systems/desktops",
        "https://smartsystems.jo/accessories/output-devices/speaker",
        "https://smartsystems.jo/accessories/consumer-electronics/power-bank-and-chargersconsumer-electronics",
        "https://smartsystems.jo/components/storage",
    ],
    "midteks": [
        "https://midteks.com/accessories-1/audio",
        "https://midteks.com/computer-systems/projector-and-monitors",
        "https://midteks.com/computer-systems/desktop",
    ],
    "cse": [
        "https://cse.jo/audio",
        "https://cse.jo/computer-systems/monitors-projectors",
        "https://cse.jo/printers-supplies",
        "https://cse.jo/computer-systems/desktop-computer",
        "https://cse.jo/accessories/mobile-accessories/power-bank",
        "https://cse.jo/components/storage-components",
        "https://cse.jo/camera-and-recorder",
    ],
    "almohanad": [
        "https://almohanadtech.com/product-category/audio-video/",
        "https://almohanadtech.com/product-category/monitors/",
        "https://almohanadtech.com/product-category/desktops/",
        "https://almohanadtech.com/product-category/networking/",
        "https://almohanadtech.com/product-category/cameras-photo/cameras/",
    ],
    "pccircle": [
        "https://pccircle.com/product-category/accessories/headphones-headset/",
        "https://pccircle.com/product-category/accessories/speakers/",
        "https://pccircle.com/product-category/components/lcd-led-monitor/",
        "https://pccircle.com/product-category/printers/",
        "https://pccircle.com/product-category/desktop-pc/",
        "https://pccircle.com/product-category/network-products/wireless/",
        "https://pccircle.com/product-category/components/solid-state-drive-ssd/",
        "https://pccircle.com/product-category/accessories/cameras/",
    ],
    "profpc": [
        "https://www.theprofpc.com/shop/monitor",
        "https://www.theprofpc.com/shop/printer-scanner",
        "https://www.theprofpc.com/shop/desktops",
        "https://www.theprofpc.com/shop/playstation-accessories/consoles",  # PS5 consoles (2026-11-25)
    ],
    "alruwwad": [
        "https://al-ruwwad.com/categories/audio-systems-accessories/6640546000000138087",
        "https://al-ruwwad.com/categories/speakers/6640546000000191775",
        "https://al-ruwwad.com/categories/monitors/6640546000000143109",
        "https://al-ruwwad.com/categories/cctv-cameras/6640546000000100035",
    ],
    "rokon": [
        "https://rokonbaghdad-jo.com/en/category/speakers", "https://rokonbaghdad-jo.com/en/category/tv-audio",
        "https://rokonbaghdad-jo.com/en/category/computer-accessories", "https://rokonbaghdad-jo.com/en/category/routers",
        "https://rokonbaghdad-jo.com/en/category/smart-devices-accessories",
    ],
    "newvision": [
        "https://newvision.jo/product-category/audio-video-and-home-theater-systems-ar/",
    ],
    "action": [
        "https://action.jo/en/category/camera",
    ],
}

# 2026-11-15: projectors, smart home, keyboards and mice, tablet pens and keyboards, graphics cards and processors
# (owner: "all of them"). Picked from a second home-page survey; City Center still left out (bot check).
ELECTRONICS_MORE = {
    "smartbuy": [
        "projectors",
        "robot-vacuum",
    ],
    "dna": [
        "tech-projectors",
    ],
    "xmart": [
        "smart-home-devices",
        "keyboards-mice",
    ],
    "igeek": [
        "graphic-cards-1",
    ],
    "estorejo": [
        "ipad-accessories",
    ],
    "compujordan": [
        "https://compujordan.com/monitor-and-display/projector-and-screen/projector",
        "https://compujordan.com/gaming-rampage/gaming-components",
        "https://compujordan.com/electronics/smart-bulb",
        "https://compujordan.com/gaming-rampage/gaming-accessories/gaming-keyboard",
        "https://compujordan.com/gaming-rampage/gaming-accessories/gaming-mouse",
        "https://compujordan.com/gaming-rampage/gaming-accessories/gaming-combo-keyboard-mouse",
    ],
    "osjo": [
        "https://os-jo.com/projector",
        "https://os-jo.com/keyboard",
        "https://os-jo.com/keyboard-and-mouse",
        "https://os-jo.com/gaming-keyboard-mouse",
        "https://os-jo.com/components",
    ],
    "midteks": [
        "https://midteks.com/computer-systems/projector-and-monitors/projector-data-show",
        "https://midteks.com/accessories-1/keyboards-and-mice",
        "https://midteks.com/gaming/gaming-keyboards-and-mice",
    ],
    "iservice": [
        "https://iservicejo.com/store/smart-home/",
    ],
    "alaryan": [
        "https://alaryanmobile.com/product-category/security-smart-home",
        "https://alaryanmobile.com/product-category/laptops-tablets/keyboard",
        "https://alaryanmobile.com/product-category/laptops-tablets/mouse",
    ],
    "action": [
        "https://action.jo/category/smart-home-appliances",
    ],
    "cse": [
        "https://cse.jo/network/smart-home",
        "https://cse.jo/accessories/computer-accessories/keyboard",
        "https://cse.jo/accessories/computer-accessories/mouse",
        "https://cse.jo/gaming/gaming-keyboard",
        "https://cse.jo/gaming/gaming-mouse",
        "https://cse.jo/components",
    ],
    "alruwwad": [
        "https://al-ruwwad.com/categories/robot-vacuum-cleaners/6640546000000657004",
        "https://al-ruwwad.com/categories/smart-home-voice-assistant/6640546000000138051",
    ],
    "ammar": [
        "https://ammarmobile.com/en-gb/category/laptop-pc-desktop-accessories-gaming-tech-jordan/laptop-desktop-accessories-gaming-office-tech-jordan/keyboards-gaming-mechanical-wireless-rgb-jordan",
        "https://ammarmobile.com/en-gb/category/pc-components-ram-gpu-cpu-storage-motherboards-jordan",
    ],
    "gts": [
        "https://gts.jo/accessories/laptop-desktop-accessories/keyboard",
        "https://gts.jo/accessories/laptop-desktop-accessories/mouse-1",
        "https://gts.jo/gaming/gaming-keyboard",
        "https://gts.jo/gaming/gaming-mouse",
        "https://gts.jo/components/computer-components",
    ],
    "smartsystems": [
        "https://smartsystems.jo/accessories/input-devices/keyboard-and-mouseinput-devices",
        "https://smartsystems.jo/components",
    ],
    "profpc": [
        "https://www.theprofpc.com/shop/graphic-card",
        "https://www.theprofpc.com/shop/cpu-processor",
    ],
}
# 2026-11-26: RAM sticks (owner: "add the ram category"). The shops' own RAM sections, found on their home pages;
# every one read once by hand first (citycenter has one too but is still left out: bot check). Server RAM is not ours.
ELECTRONICS_MORE_RAM = {
    "gts": ["https://gts.jo/components/ram/ram-for-desktop", "https://gts.jo/components/ram/ram-for-laptop"],
    "compujordan": ["https://compujordan.com/computer-hardware/components/memory-ram",
                    "https://compujordan.com/gaming-rampage/gaming-components/gaming-memory-ram"],
    "osjo": ["https://os-jo.com/desktop-memory", "https://os-jo.com/laptop-memory"],
    "smartsystems": ["https://smartsystems.jo/components/core-system-components-components/memory-ram-core-system-components"],
    "midteks": ["https://midteks.com/computer-components/core-components/memory"],
    "cse": ["https://cse.jo/components/system-memory-rams"],
    "numberone": ["https://numberonestore.net/components/ram"],
}
# 2026-11-27 (owner: "add the ram sections of all the shops ... I don't want this case to happen ever again"): every
# section of our kinds on the shops' menus that we did not read (pricecompare/sections.py finds them; nightly
# `cli sections`, judged by the daily doctor). Each one's first page was read once and kept only when at least
# 3 items and 30% of it are products we show. City Center (owner: "all sections for all shops"): read signed as
# DerbaniBot; its printers page answers with Cloudflare's bot check (left out); a refusal rests only these sections.
ELECTRONICS_MORE_SECTIONS = {
    "citycenter": [
        "https://citycenter.jo/computer-hardware-audio/audio-speaker-and-headset",
        "https://citycenter.jo/electronics/electronics-camera",
        "https://citycenter.jo/pc-and-laptops/pc-and-laptops-desktops",
        "https://citycenter.jo/pc-and-laptops/pc-and-laptops-laptops",
        "https://citycenter.jo/computer-hardware-monitor-and-display",
        "https://citycenter.jo/computer-hardware/computer-hardware-monitor-and-display",
        "https://citycenter.jo/computer-hardware/components-cpu-and-processor",
        "https://citycenter.jo/computer-hardware/components-video-card",
        "https://citycenter.jo/computer-hardware-peripherals/peripherals-combo",
        "https://citycenter.jo/computer-hardware-peripherals/peripherals-keyboard",
        "https://citycenter.jo/computer-hardware-peripherals/peripherals-mouse",
        "https://citycenter.jo/computer-hardware-peripherals/batteries-power-banks-chargers/power-banks",
        "https://citycenter.jo/electronics/computer-hardware-projector-and-screen",
        "https://citycenter.jo/computer-hardware/components-memory-ram",
        "https://citycenter.jo/Networking",
        "https://citycenter.jo/electronics/electronics-smart-home",
        "https://citycenter.jo/computer-hardware-storage",
        "https://citycenter.jo/computer-hardware/components-solid-state-drive-ssd",
        "https://citycenter.jo/gaming-storage-drive/ssds",
    ],
    "iservice": [
        "https://iservicejo.com/store/accessories/earbuds/",
        "https://iservicejo.com/store/mobile-phones/google/",
        "https://iservicejo.com/store/mobile-phones/redmi/",
        "https://iservicejo.com/store/mobile-phones/vivo/",
        "https://iservicejo.com/store/mobile-wi-fi/",
        "https://iservicejo.com/store/accessories/smart-watches/",
    ],
    "leaders": [
        "https://leaders.jo/en/product-category/all-products/electronics/mobiles/airpods-and-mobile-headphones/",
        "https://leaders.jo/en/product-category/all-products/home-appliance/vacuum-cleaners-household-appliances/smart-vacuum/",
        "https://leaders.jo/en/product-category/all-products/electronics/smartwatches-and-accessories/smart-watch/",
    ],
    "ammar": [
        "https://ammarmobile.com/en-gb/category/laptop-pc-desktop-accessories-gaming-tech-jordan/laptop-desktop-accessories-gaming-office-tech-jordan/headsets-gaming-wireless-wired-bluetooth-headsets-usb",
        "https://ammarmobile.com/en-gb/category/laptop-pc-desktop-accessories-gaming-tech-jordan/laptop-desktop-accessories-gaming-office-tech-jordan/computer-mouse-gaming-wireless-ergonomic-rgb-jordan",
    ],
    "gts": [
        "https://gts.jo/gaming/gaming-headset",
        "https://gts.jo/computers/all-in-one",
        "https://gts.jo/gaming/gaming-laptops",
        "https://gts.jo/network-ups/access-point-and-extender",
        "https://gts.jo/network-ups/routers",
        "https://gts.jo/components/flash-memory-card",
        "https://gts.jo/components/internal-storage",
    ],
    "bci": [
        "https://jo.bcitechstore.com/product-category/office-tools/office-essentials/keyboards-mouse/",
        "https://jo.bcitechstore.com/product-category/xiaomi-robot-vacuums/",
        "https://jo.bcitechstore.com/product-category/blackview/",
        "https://jo.bcitechstore.com/product-category/tablets-redmi/",
        "https://jo.bcitechstore.com/product-category/tv-media/",
        "https://jo.bcitechstore.com/product-category/tvs-av/",
    ],
    "numberone": [
        "https://numberonestore.net/earphone-wired",
        "https://numberonestore.net/earphone-wireless",
        "https://numberonestore.net/gaming-headset",
        "https://numberonestore.net/wired-headset",
        "https://numberonestore.net/wireless-headset",
        "https://numberonestore.net/monitors",
        "https://numberonestore.net/graphics-cards",
        "https://numberonestore.net/gaming-keyboard",
        "https://numberonestore.net/gaming-mouse",
        "https://numberonestore.net/keyboard",
        "https://numberonestore.net/mouse-computer",
        "https://numberonestore.net/office-mouse",
        "https://numberonestore.net/office_keyboard",
    ],
    "rokon": [
        "https://rokonbaghdad-jo.com/en/category/smart-home-networking",
    ],
    "compujordan": [
        "https://compujordan.com/gaming-rampage/gaming-pc-and-laptops",
        "https://compujordan.com/pc-and-laptops/mini-pc",
        "https://compujordan.com/computer-hardware/components/cpu",
        "https://compujordan.com/computer-hardware/components/graphic-card",
        "https://compujordan.com/computer-hardware/computer-accessories/combo-keyboard-mouse",
        "https://compujordan.com/computer-hardware/computer-accessories/keyboard",
        "https://compujordan.com/computer-hardware/computer-accessories/mouse",
    ],
    "osjo": [
        "https://os-jo.com/gaming-headset",
        "https://os-jo.com/headset",
        "https://os-jo.com/all-in-one-computer",
        "https://os-jo.com/business-laptops",
        "https://os-jo.com/gaming-laptops",
        "https://os-jo.com/home-laptops",
        "https://os-jo.com/laptops-desktops-promotions",
        "https://os-jo.com/monitors-promotions",
        "https://os-jo.com/cpu-prossesors",
        "https://os-jo.com/graphics-cards",
        "https://os-jo.com/keyboard-mouse-combo",
        "https://os-jo.com/mouse",
        "https://os-jo.com/inkjet-printer",
        "https://os-jo.com/laser-printers",
        "https://os-jo.com/speakers",
        "https://os-jo.com/external-hard-drive",
        "https://os-jo.com/hdd-storage",
        "https://os-jo.com/solid-state-drive-ssd",
        "https://os-jo.com/usb-and-memory-cards",
        "https://os-jo.com/tablet",
    ],
    "smartsystems": [
        "https://smartsystems.jo/accessories/output-devices/head-set",
    ],
    "midteks": [
        "https://midteks.com/gaming/gaming-headset",
        "https://midteks.com/gaming/gaming-monitors",
        "https://midteks.com/computer-components/core-components/cpus-processors",
        "https://midteks.com/printers-scanners",
        "https://midteks.com/gaming/gaming-memory",
        "https://midteks.com/computer-components/storage-devices",
        "https://midteks.com/gaming/gaming-ssd",
        "https://midteks.com/computer-components/core-components/graphic-cards",
    ],
    "cse": [
        "https://cse.jo/gaming/gaming-headset",
        "https://cse.jo/network/access-point-range-extender",
        "https://cse.jo/network/routers",
        "https://cse.jo/network/vpn-router",
    ],
    "almohanad": [
        "https://almohanadtech.com/product-category/cameras-photo/microsd/",
        "https://almohanadtech.com/product-category/printers-scanners/",
    ],
    "newton": [
        "https://newtonstores.com/shop/category/mobiles-electronics-43",
        "https://newtonstores.com/shop/category/tvs-home-theatres-38",
    ],
    "profpc": [
        "https://www.theprofpc.com/shop/networking",
        "https://www.theprofpc.com/shop/storage-drive",
        "https://www.theprofpc.com/shop/memory-ram",
    ],
    "alruwwad": [
        "https://al-ruwwad.com/categories/analog-cameras/6640546000000143212",
        "https://al-ruwwad.com/categories/cameras-system/6640546000000093523",
        "https://al-ruwwad.com/categories/indoor-wireless-cameras/6640546000000143230",
        "https://al-ruwwad.com/categories/ip-cameras/6640546000000143218",
        "https://al-ruwwad.com/categories/outdoor-wireless-cameras/6640546000000143236",
        "https://al-ruwwad.com/categories/access-point/6640546000000191758",
        "https://al-ruwwad.com/categories/routers/6640546000000191752",
        "https://al-ruwwad.com/categories/wi-fi-networking/6640546000000138075",
        "https://al-ruwwad.com/categories/wifi-camersa/6640546000000100023",
        "https://al-ruwwad.com/categories/wifi-extender/6640546000000191746",
        "https://al-ruwwad.com/categories/security-camera-alarm-systems/6640546000000143126",
        "https://al-ruwwad.com/categories/tv-screen/6640546000000138027",
    ],
}
for _shop, _more in (*ELECTRONICS_MORE_RAM.items(), *ELECTRONICS_MORE_SECTIONS.items()):
    ELECTRONICS_MORE.setdefault(_shop, []).extend(u for u in _more if u not in ELECTRONICS_MORE.get(_shop, []))
for _shop, _more in ELECTRONICS_MORE.items():
    ELECTRONICS.setdefault(_shop, []).extend(u for u in _more if u not in ELECTRONICS.get(_shop, []))


# 2026-11-27 (owner: "read all the products from their shop"): products no listing page of ours shows, read from the
# shop's sitemap and their own product pages (collectors/pages.py), this many pages per run (--part pages, with the
# 6-hourly electronics job). Shops whose product pages carry schema.org Product data; checked by hand on 3 pages each.
# City Center most of all: its robots.txt forbids ?page=, so its listings show only their first 20 items.
PAGES = {"citycenter": 450, "gts": 120, "osjo": 120, "midteks": 120, "numberone": 100, "leaders": 100, "platinum": 100,
         "cse": 80, "smartsystems": 60, "alaryan": 40, "almohanad": 40, "ammar": 30, "h4m": 30, "newvision": 10,
         "darwish": 100, "bci": 60, "newton": 60}   # 2026-11-27: their own page kinds (Magento, WooCommerce, Odoo)


def fetch_pages(slug: str, client: PoliteClient) -> list:
    from sqlalchemy import select as _select
    from .db.models import Offer as _Offer, Store as _Store
    from .display import LIVE_CATEGORIES
    base = SOURCES[slug][1]
    with make_session(get_engine()) as s:
        store = s.scalar(_select(_Store).where(_Store.slug == slug))
        rows = s.execute(_select(_Offer.url, _Offer.external_id, _Offer.last_checked).where(_Offer.store_id == store.id)).all() if store else []
    held = {pages._key(u): t.timestamp() for u, e, t in rows if e.startswith(pages.PREFIX) and t}
    listed = {pages._key(u) for u, e, _ in rows if not e.startswith(pages.PREFIX)}
    return pages.collect(client, base, LIVE_CATEGORIES, held, listed, PAGES[slug])


class PartialRead(Exception):
    """The shop said "slow down" part-way: the pages read before it are kept and saved."""

    def __init__(self, offers, error: Exception):
        super().__init__(str(error))
        self.offers, self.error = offers, error


def read_json(path: Path) -> dict:
    import json
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def fetch_offers(slug: str, client: PoliteClient, part: str = "main"):
    _, base, method, _, params = SOURCES[slug]
    if method == "shopify_json":  # the whole catalogue in one list, a few pages a run (see shopify.collect_pages)
        if part == "electronics":
            return []
        pages = read_json(SHOPIFY_PAGES_FILE)
        offers, pages[slug], error = shopify.collect_pages(client, base, pages.get(slug, 1), SHOPIFY_PAGES_PER_RUN)
        write_json(SHOPIFY_PAGES_FILE, pages)
        if error:
            raise PartialRead(offers, error)
        return offers
    if part == "pages":
        return fetch_pages(slug, client) if slug in PAGES else []
    if part == "electronics":   # the same reader, pointed at the shop's electronics sections only
        if method == "sitemap_pages":
            return platinum.collect(client, base, part="electronics")
        if slug not in ELECTRONICS:
            return []
        params = {"handles" if method == "shopify_json" else "listings": ELECTRONICS[slug]}
    if method == "shopify_json":
        out = []
        for h in params["handles"]:
            out.extend(shopify.collect(client, base, h))
        return out
    if method == "woocommerce_html":
        return woocommerce.collect(client, slug, params["listings"])
    if method == "nuxt_html":
        out = {}
        for listing in params["listings"]:
            for o in action.collect(client, base, listing):
                out[o.external_id] = o
        return list(out.values())
    if method in ("odoo_html", "site123_html", "zoho_html"):
        return stores.collect(client, method.split("_")[0], base, params["listings"])
    if method == "aiz_html":
        return aiz.collect(client, params["listings"])
    if method == "opencart_html":
        return opencart.collect(client, params["listings"])
    if method == "darwish_sitemap":
        return darwish.collect(client, base)
    return platinum.collect(client, base)


BLOCK_REST = timedelta(days=3)  # a shop that refused us (bot check, 403, 429) is left alone this long, then tried once


def refused(e: Exception) -> bool:
    """The shop said no to our reader. We never try another way: we stop, rest, and the owner decides."""
    import httpx

    from .collectors.base import ChallengeBlocked, RobotsBlocked
    return isinstance(e, (ChallengeBlocked, RobotsBlocked)) or (isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (403, 429))


# Shopify counts one visitor's requests over ALL its shops together. 2026-11-18: 30 s apart per shop, with the five
# Shopify shops read one after another, still got "slow down" on the 2nd page every run, so nothing was saved for a day.
# Now: 75 s between any two Shopify requests from this computer (one shared pace for every shop and job), at most
# 3 pages a run, each page kept, and the next run carries on where this one stopped.
SHOPIFY_INTERVAL = 75.0
# 2026-11-23: run after run the 1st page answered and the 2nd got the 429 that rests the shop 6 h or more, so a shop's
# ~10-20 pages took 2-3 days (prices went stale). Now one page a run and robots.txt kept 24 h.
# 2026-11-24: one run an hour was too often (all five shops said 429 an hour after answering): every 3 hours (pc_jobs).
SHOPIFY_PAGES_PER_RUN = 1
SHOPIFY_PACE_FILE = Path.home() / ".derbani" / "shopify_pace.txt"
SHOPIFY_PAGES_FILE = Path.home() / ".derbani" / "shopify_pages.json"
# Shopify keeps a home connection on "slow down" for hours after too many requests, and every try restarts that:
# after a 429 a Shopify shop rests 6 hours, and is never retried within the same read (2026-11-17)
SHOPIFY_LIMIT_REST = timedelta(hours=5, minutes=30)  # 6 h missed the 3-hourly turn by a minute (2026-11-18)
LIMIT_REST = timedelta(hours=2)   # "too many requests, retry in 60 s" (429): a short pause, not a refusal


def rate_limited(e: Exception) -> bool:
    """A short pause, not a refusal: "too many requests" (429), or robots.txt said no or could not be read this time
    (PC Circle 2026-11-14: its robots.txt allows the page, the request for it failed once). We stay out and try in 2 hours."""
    import httpx

    from .collectors.base import RobotsBlocked
    return isinstance(e, RobotsBlocked) or isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429


# shops whose bot check refuses us often: after a refusal they are tried once a week, not every 3 days
# (empty: owner 2026-11-15 chose "one try every few days" for Darwish too, the usual 3 days)
REST_AFTER_REFUSAL: dict[str, timedelta] = {}


# between two answered reads of a Shopify shop, also when a missed turn was made up by hand (2026-11-25)
SHOPIFY_GAP = timedelta(hours=2, minutes=50)
SHOPIFY_REST_CAP = timedelta(hours=47, minutes=30)


def shopify_rest(streak: int = 1) -> timedelta:
    """Shopify keeps saying 429 to a reader it has marked (no answer 17-19 Nov 2026 at one try per 5 h 30): every
    429 in a row doubles the wait, 5:30, 11:30, 23:30, then 47:30 at most (30 min short of a 3-hourly turn)."""
    return min(timedelta(hours=6) * 2 ** (max(streak, 1) - 1) - timedelta(minutes=30), SHOPIFY_REST_CAP)


def limited_streak(s, store_id: int) -> int:
    """How many of the shop's latest runs in a row were a 429 that brought back nothing."""
    n = 0
    for r in s.query(CollectionRun).filter_by(store_id=store_id).order_by(CollectionRun.started_at.desc()).limit(8):
        if r.status != "limited" or (r.items_seen or 0) > 0:
            break
        n += 1
    return n


def rest_for(run, slug: str = "", streak: int = 1) -> timedelta | None:
    """How long a shop rests after its last run: 3 days after a refusal (bot check, 403), 2 hours after a busy-signal
    (429, the shop's own rate limit, which says to come back in a minute). Older 429 runs were saved as "blocked"."""
    if run is None:
        return None
    if run.status == "limited" or run.status == "blocked" and "429" in (run.error or ""):
        return shopify_rest(streak) if SOURCES.get(slug, ("", "", ""))[2] == "shopify_json" else LIMIT_REST
    if run.status == "ok" and SOURCES.get(slug, ("", "", ""))[2] == "shopify_json":
        return SHOPIFY_GAP
    return REST_AFTER_REFUSAL.get(slug, BLOCK_REST) if run.status == "blocked" else None


def resting(s, store_id: int, now: datetime, slug: str = "") -> bool:
    last = s.query(CollectionRun).filter_by(store_id=store_id).order_by(CollectionRun.started_at.desc()).first()
    rest = rest_for(last, slug, limited_streak(s, store_id))
    if rest is None:
        return False
    at = last.started_at if last.started_at.tzinfo else last.started_at.replace(tzinfo=timezone.utc)
    return now - at < rest


# besides the Shopify shops: shops whose gate may know a signed reader (PC Circle and City Center: Cloudflare)
SIGNED = {"pccircle", "citycenter"}
# A refusal (bot check, 403) on a shop's extra sections (--part electronics) rests only those sections, not the shop's
# phones and tablets (2026-11-27, owner: "handle all sections for all shops"; City Center's gate refuses some
# sections now and then). {shop: ISO time the extra sections may be tried again}
EXTRA_REST_FILE = Path.home() / ".derbani" / "extra_rest.json"


def run_source(slug: str, dry_run: bool, part: str = "main") -> None:
    name, base, method, rating, _ = SOURCES[slug]
    # Shopify counts requests per visitor address across all its shops and answers a home connection "slow down,
    # retry after 60 s" beyond ~2-3 product lists a minute (2026-11-17): 30 s apart
    shopify_shop = method.startswith("shopify")
    client = PoliteClient(min_interval=SHOPIFY_INTERVAL if shopify_shop else 3.0, max_retries=0 if shopify_shop else 3,
                          shared_pace=SHOPIFY_PACE_FILE if shopify_shop else None, sign=shopify_shop or slug in SIGNED)
    if not dry_run:
        engine = get_engine()
        init_db(engine)
        with make_session(engine) as s:
            store = ensure_store(s, slug, name, base, method, rating)
            until = read_json(EXTRA_REST_FILE).get(slug) if part != "main" else None
            if until and datetime.fromisoformat(until) > datetime.now(timezone.utc):
                print(f"{slug}: extra sections resting after the shop's refusal; tried again after {until}")
                return
            if resting(s, store.id, datetime.now(timezone.utc), slug):
                last = s.query(CollectionRun).filter_by(store_id=store.id).order_by(CollectionRun.started_at.desc()).first()
                print(f"{slug}: resting after the shop's last answer ({last.status}); tried again after {rest_for(last, slug, limited_streak(s, store.id))}")
                return
    partial = None
    shopify_page = read_json(SHOPIFY_PAGES_FILE).get(slug, 1) if shopify_shop else 1   # the page this run starts at
    try:
        try:
            raw = fetch_offers(slug, client, part)
        except PartialRead as p:
            raw, partial = p.offers, p.error
        # one listing can sit in two of a shop's sections (SmartBuy "laptops" and "notebooks"): keep it once
        offers = list({o.external_id: o for o in raw}.values())
    except Exception as e:  # a crash must show up in the run log, or reliability numbers lie
        blocked = refused(e)
        if blocked and not rate_limited(e) and part != "main":
            if not dry_run:
                until = datetime.now(timezone.utc) + REST_AFTER_REFUSAL.get(slug, BLOCK_REST)
                write_json(EXTRA_REST_FILE, read_json(EXTRA_REST_FILE) | {slug: until.isoformat()})
            print(f"{slug}: the shop refused our reader on its extra sections ({type(e).__name__}: {str(e)[:80]}); "
                  f"those rest {REST_AFTER_REFUSAL.get(slug, BLOCK_REST).days} days, its main sections go on")
            return
        if not dry_run:
            engine = get_engine()
            init_db(engine)
            with make_session(engine) as s:
                store = ensure_store(s, slug, name, base, method, rating)
                src = s.query(Source).filter_by(store_id=store.id).one()
                src.consecutive_failures = (src.consecutive_failures or 0) + 1
                status = ("limited" if rate_limited(e) else "blocked") if blocked else "failed"
                after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
                note = f" (retry-after {after})" if after else ""
                s.add(CollectionRun(store_id=store.id, requests=client.request_count, status=status,
                                    finished_at=datetime.now(timezone.utc), error=f"{type(e).__name__}: {e}{note}"[:500]))
                s.commit()
                streak = limited_streak(s, store.id)
                if status == "limited" and shopify_shop and shopify_page > 1 and streak >= 3:
                    # the same late page refused three times over days (2026-11-24: four shops stood at page 9-10 while
                    # pages 1-8 went stale): after its rest the list starts again at page 1. Not asked any sooner.
                    write_json(SHOPIFY_PAGES_FILE, read_json(SHOPIFY_PAGES_FILE) | {slug: 1})
        else:
            streak = 1
        if blocked:  # not a fault of ours: recorded and shown on the dashboard, the job itself carries on green
            if rate_limited(e):
                print(f"{slug}: the shop asked us to slow down (429); stopped politely, trying again in {rest_for(CollectionRun(status="limited"), slug, streak)}")
            else:
                print(f"{slug}: the shop refused our reader ({type(e).__name__}); stopped politely, resting {REST_AFTER_REFUSAL.get(slug, BLOCK_REST).days} days")
            return
        raise
    print(f"{slug}: {len(offers)} offers, {client.request_count} requests")
    for o in offers[:5]:
        print(" ", o.price_jod, o.in_stock, o.title)
    if dry_run:
        return
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        store = ensure_store(s, slug, name, base, method, rating)
        src = s.query(Source).filter_by(store_id=store.id).one()
        if not src.enabled:
            print("source disabled, skipping")
            return
        run = CollectionRun(store_id=store.id, requests=client.request_count)
        s.add(run)
        if not offers and client.request_count > 0 and shopify_page == 1:   # a later page of only cases and cables is normal
            # pages answered but no product was read: the shop most likely changed its page design (Oriental Store,
            # 2026-11-15). Recorded as a failure so the dashboard and the health check show it at once; its last prices stay.
            run.status, run.finished_at = "failed", datetime.now(timezone.utc)
            run.error = f"0 products read from {client.request_count} pages: the shop's page design may have changed ({part} part)"
            src.consecutive_failures = (src.consecutive_failures or 0) + 1
            s.commit()
            print(f"::warning::{slug}: {run.error}")
            return
        save_offers(s, store, offers, run)
        run.status, run.finished_at = "ok", datetime.now(timezone.utc)
        src.consecutive_failures = 0
        if partial is not None:  # the pages read are saved; the shop then said "slow down": it rests as after any 429
            run.status, run.error = "limited", f"after {len(offers)} offers: {type(partial).__name__}: {partial}"[:500]
        s.commit()
        print(f"saved: {run.items_seen} seen, {run.items_changed} changed" + (" (then asked to slow down; resting)" if partial else ""))


@contextmanager
def build_lock(path: Path, wait_max: float = 1800, stale_after: float = 3600):
    """Only one site build at a time; a second one waits (up to 30 min). A lock left by a crashed build expires."""
    path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale_after:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() - start > wait_max:
                raise SystemExit("another site build is still running; try again later")
            time.sleep(5)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def swap_in(fresh: Path, live: Path) -> None:
    """Put a finished build in place of the old one in one step (the old one is removed afterwards)."""
    import shutil
    old = live.with_name(live.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    for attempt in range(10):  # Windows: a file still open elsewhere (a deploy reading it) can block a rename for a moment
        try:
            if live.exists():
                live.rename(old)
            fresh.rename(live)
            break
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(3)
    shutil.rmtree(old, ignore_errors=True)


def run_matching(cmd: str, ids: list[int] | None = None) -> None:
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        if cmd == "push-health":
            from . import health
            health.main(s)
            return
        if cmd == "fix-mixed":   # listings that belong to another product are held, held ones let back (2026-11-22)
            from .matching.mixed import fix_mixed
            r = fix_mixed(s)
            s.commit()
            for k in ("held", "back"):
                for line in r[k]:
                    print(f"{k}: {line}")
            print(f"fix-mixed: {len(r['held'])} held, {len(r['back'])} back")
            return
        if cmd == "shop-check":   # ~/.derbani/shop_problems.json, read by the daily repair session (2026-11-21)
            from . import health
            problems = health.write_shop_problems(s)
            for p in problems:
                print(f"{p['shop']}: {p['kind']} - {p['detail']}")
            print(f"shop-check: {len(problems)} problem(s), {sum(p['kind'] == 'broken' for p in problems)} broken")
            return
        if cmd in ("apart", "apart-seen"):     # far-apart prices nobody has looked at (2026-11-25): read by the daily doctor
            from .matching import apart
            print(f"apart: {apart.mark_seen()} products marked as looked at" if cmd == "apart-seen"
                  else f"apart: {apart.write(s)} products to look at")
            return
        if cmd == "apart-same":                # these products' listings were read: one product, whatever the prices (2026-11-25)
            from .matching import sure
            print(f"apart-same: {sure.mark(s, ids)} titles added to data/sure.json")
            return
        if cmd in ("missed", "missed-seen"):   # hidden in-stock titles nobody has looked at (2026-11-25): read by the daily doctor
            from .matching import missed
            if cmd == "missed-seen":
                print(f"missed: {missed.mark_seen()} titles marked as looked at")
            else:
                print("missed:", missed.write(s))
            return
        if cmd == "propose-catalog":
            for brand, family, n in matcher.propose_catalog(s):
                print(f"{brand},{family},{n}")
            return
        if cmd == "report":
            import json
            print(json.dumps(report.compute(s), indent=2))
            return
        if cmd == "build-site":
            from . import site
            print("variants on page:", site.build(s, Path(__file__).resolve().parents[2] / "site"))
            return
        if cmd == "build-web":
            from . import website
            root = Path(__file__).resolve().parents[2]
            from sqlalchemy import select as _select

            from .db.models import Store as _Store
            sites = {name: url for name, url in s.execute(_select(_Store.name, _Store.site_url)).all()}
            # One build at a time (the hourly job and a hand-run build once emptied the same folder together,
            # 2026-11-18), and the finished site replaces web_build in one step, so nothing ever sees half a site.
            with build_lock(root / "logs" / ".build-web"):
                fresh = root / "web_build.new"
                stats = website.build(s, fresh, root / "web", shop_sites=sites)
                print("website:", stats)
                if stats["products"] < 50:  # never publish a nearly empty site over the real one
                    raise SystemExit("too few products for a website build; not publishing")
                from . import api_static  # the app's data as files on kamkam.derbani.com (served instantly, never sleeps)
                print("app files:", api_static.build(fresh, data=website.LAST_DATA))
                swap_in(fresh, root / "web_build")
            return
        if cmd == "deal-cards":
            from datetime import datetime as _dt, timezone as _tz

            from . import deal_cards
            from .display import LIVE_CATEGORIES as _LIVE
            from .views import build_variant_data
            now = _dt.now(_tz.utc)
            data = [v for v in build_variant_data(s, now) if v["best_price"] is not None and v["category"] in _LIVE]
            print("deal cards:", deal_cards.make(data, now))
            return
        if cmd in ("indexnow-prepare", "indexnow-send"):
            from . import indexnow
            root = Path(__file__).resolve().parents[2]
            listing = root / "indexnow-urls.txt"
            if cmd == "indexnow-prepare":
                print("new addresses:", indexnow.prepare(root / "web_build" / "sitemap.xml", listing))
            else:
                print("indexnow answer:", indexnow.send(listing))
            return
        if cmd == "audit-sample":
            for row in report.audit_sample(s):
                print(" | ".join(str(x) for x in row))
            return
        if cmd == "grow-catalog":
            print("families appended:", matcher.grow_catalog(s, CATALOG_CSV))
            return
        if cmd == "seed-catalog":
            print("models added:", matcher.load_catalog(s, CATALOG_CSV), "from the register:", matcher.load_register(s))
        else:
            print(matcher.match_offers(s, new_only=cmd == "match-new"))
        s.commit()


def run_grow(dry_run: bool, block: list[str] | None, rematch: bool = False) -> None:
    """Nightly: add new models that several shops agree on (see matching/grow.py). --block undoes one."""
    import json, os
    from .matching import grow
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        if block:
            print("listings back to review:", grow.block_model(s, block[0], block[1]))
            s.commit()
            return
        r = grow.auto_grow(s, dry_run=dry_run)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        if not dry_run:
            s.commit()
            if rematch and r["added"]:  # only new models need the review queue read again
                print(matcher.match_offers(s))
                s.commit()
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:  # shown on the run's page
            with open(summary, "a", encoding="utf-8") as f:
                lines = "".join(f"- {x}\n" for x in r["added"]) or "none\n"
                f.write("## New products added to the catalog\n" + lines)
                f.write("\n## Not added yet (checked again every night)\n" + "".join(f"- {x}\n" for x in r["not_yet"]))


def main() -> None:
    ap = argparse.ArgumentParser(prog="pricecompare")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("source", choices=sorted(SOURCES))
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--part", choices=["main", "electronics", "pages"], default="main")
    cr = sub.add_parser("clicks-report", help="private Go-to-shop click report (private project only)")
    cr.add_argument("--csv", help="also save the raw counts to this file")
    sr = sub.add_parser("shop-reports", help="monthly visitors-sent report per shop (private, ~/Derbani shop reports)")
    sr.add_argument("--month", help="YYYY-MM (default: last month)")
    g = sub.add_parser("auto-grow")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--match", action="store_true", help="match again when models were added")
    g.add_argument("--block", nargs=2, metavar=("BRAND", "FAMILY"), help="remove a wrong model for good")
    for name in ("propose-catalog", "grow-catalog", "seed-catalog", "match", "match-new", "report", "audit-sample", "build-site", "build-web", "deal-cards", "indexnow-prepare", "indexnow-send", "push-health", "fix-images", "shop-specs", "maker-specs", "shop-check", "fix-mixed", "missed", "missed-seen", "apart", "apart-seen", "search-check"):
        sub.add_parser(name)
    sub.add_parser("sections", help="shop sections of our kinds we do not read -> ~/.derbani/missed_sections.json")
    ss = sub.add_parser("sections-seen", help="sections looked at and left out on purpose (data/sections_seen.json)")
    ss.add_argument("why")
    ss.add_argument("urls", nargs="+")
    sub.add_parser("apart-same", help="these products' listings are one product each").add_argument("ids", nargs="+", type=int)
    a = ap.parse_args()
    if a.command == "apart-same":
        return run_matching(a.command, a.ids)
    if a.command == "collect":
        run_source(a.source, a.dry_run, a.part)
    elif a.command == "clicks-report":
        from . import clicks
        clicks.main(a.csv)
    elif a.command == "shop-reports":
        from . import shop_reports
        shop_reports.main(a.month)
    elif a.command == "sections":   # nightly: shop sections of our kinds that we do not read (2026-11-27)
        import json
        from . import sections
        print("sections:", json.dumps(sections.write(), ensure_ascii=False))
    elif a.command == "sections-seen":
        from . import sections
        print("sections-seen:", sections.mark_seen(a.urls, a.why))
    elif a.command == "search-check":   # nightly: real searches on the site's, the app's and the API's rules (2026-11-25)
        import json
        from . import search_check
        print("search-check:", json.dumps(search_check.write(), ensure_ascii=False))
    elif a.command == "shop-specs":
        from . import shop_specs
        shop_specs.read_pages()
    elif a.command == "maker-specs":
        from . import maker_specs
        maker_specs.run()
    elif a.command == "fix-images":
        from . import image_fixes
        image_fixes.main()
    elif a.command == "auto-grow":
        run_grow(a.dry_run, a.block, a.match)
    else:
        run_matching(a.command)


if __name__ == "__main__":
    main()

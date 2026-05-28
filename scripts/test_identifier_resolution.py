import asyncio

from printerprinter.bambuddy_client import BambuddyClient
from printerprinter.config import get_settings
from printerprinter.main import _parse_monitored_identifiers


async def main() -> None:
    s = get_settings()
    client = BambuddyClient(
        base_url=str(s.bambuddy_base_url),
        api_token=s.bambuddy_api_token,
        timeout_seconds=s.bambuddy_timeout_seconds,
        auth_mode=s.bambuddy_auth_mode,
        auth_header_name=s.bambuddy_auth_header_name,
        jobs_endpoint=s.bambuddy_jobs_endpoint,
        printers_endpoint=s.bambuddy_printers_endpoint,
        printer_status_endpoint_template=s.printer_status_endpoint_template,
    )
    printers = await client.list_printers()
    selectors = _parse_monitored_identifiers(s.monitored_printer_identifiers)

    print("selectors", sorted(selectors))
    matches = []
    for p in printers:
        keys = {p.printer_id.lower()}
        if p.name:
            keys.add(p.name.lower())
        if p.serial_number:
            keys.add(p.serial_number.lower())
        if p.ip_address:
            keys.add(p.ip_address.lower())
        if keys.intersection(selectors):
            matches.append((p.printer_id, p.name, p.ip_address, p.serial_number))

    print("match_count", len(matches))
    for row in matches:
        print("match", row)


if __name__ == "__main__":
    asyncio.run(main())

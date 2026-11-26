def account(supply: float, demand: float, throughput: float, hours: int, cfg: dict, slot: int = 0) -> dict:
    attempted = min(supply, demand)
    if min(supply, demand, throughput, hours) < 0 or throughput > attempted + 1e-8:
        raise ValueError("Inconsistent slot flow")
    inspected = min(throughput, hours * cfg["processing_per_crew_hour"])
    intercepted = inspected * cfg["detection_probability"]
    utilization = inspected/(hours*cfg["processing_per_crew_hour"]) if hours else 0.
    arrivals = cfg.get("hourly_civilian_arrivals",[cfg["civilian_arrivals"]])
    traffic_delay = hours * arrivals[slot % len(arrivals)] * cfg["minutes_per_arrival"] * (1+utilization)/2
    return dict(supply=supply, delivered=throughput-intercepted, intercepted=intercepted,
                deferred=max(0., attempted-throughput), undeparted=supply-attempted,
                officer_hours=hours * cfg["officers_per_site"],
                civilian_delay=traffic_delay)

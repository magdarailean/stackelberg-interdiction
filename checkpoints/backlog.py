from .accounting import account
from .follower import Scenario


def carry_day(day,plan,factor,cfg):
    backlog = delivered = intercepted = undeparted = supply_total = 0.
    for t,slot in enumerate(day):
        graph = slot.graph.copy()
        supply = graph.out_degree(slot.source,weight="capacity")
        demand = graph.in_degree(slot.sink,weight="capacity")
        supply_total += supply
        for edges,total in ((graph.out_edges(slot.source,data=True),supply),
                            (graph.in_edges(slot.sink,data=True),demand)):
            for _,_,arc in edges:
                if total:
                    arc["capacity"] += backlog*arc["capacity"]/total
        active = frozenset(e for hour,e in plan if hour==t)
        flow = Scenario(graph,slot.source,slot.sink).delivered(active,factor)
        outcome = account(supply+backlog,demand+backlog,flow,len(active),cfg,t)
        delivered += outcome["delivered"]
        intercepted += outcome["intercepted"]
        undeparted += outcome["undeparted"]
        backlog = outcome["deferred"]
    if abs(supply_total-delivered-intercepted-undeparted-backlog)>1e-7:
        raise ValueError("Daily supply balance failed")
    return delivered,backlog

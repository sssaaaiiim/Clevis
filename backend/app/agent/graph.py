"""One compiled async graph; dependencies are injected per task, not checkpointed."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import routing
from app.agent.nodes.approval_gate import approval_gate_node
from app.agent.nodes.executor import executor_node
from app.agent.nodes.finish import finish_node
from app.agent.nodes.navigator import navigator_node
from app.agent.nodes.next_sub_goal import next_sub_goal_node
from app.agent.nodes.outcome_check import outcome_node
from app.agent.nodes.planner import planner_node
from app.agent.nodes.policy_check import policy_node
from app.agent.nodes.revise import revise_node
from app.agent.state import AgentState

CompiledGraph = CompiledStateGraph[AgentState, None, AgentState, AgentState]
checkpointer = MemorySaver()


def build_graph() -> CompiledGraph:
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("navigator", navigator_node)
    builder.add_node("policy_check", policy_node)
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("executor", executor_node)
    builder.add_node("outcome_check", outcome_node)
    builder.add_node("revise", revise_node)
    builder.add_node("next_sub_goal", next_sub_goal_node)
    builder.add_node("finish", finish_node)
    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", routing.after_planner)
    builder.add_conditional_edges("navigator", routing.after_navigator)
    builder.add_conditional_edges("policy_check", routing.after_policy)
    builder.add_conditional_edges("approval_gate", routing.after_approval)
    builder.add_conditional_edges("executor", routing.after_executor)
    builder.add_conditional_edges("outcome_check", routing.after_outcome)
    builder.add_conditional_edges("revise", routing.after_revise)
    builder.add_conditional_edges("next_sub_goal", routing.after_next)
    builder.add_conditional_edges(
        "finish", routing.after_finish, {"navigator": "navigator", END: END}
    )
    return builder.compile(checkpointer=checkpointer)


agent_graph = build_graph()

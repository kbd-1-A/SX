"""可预期的 Agent 故障类型。

把模型层异常转换成稳定、可展示给用户的错误信息；详细原因只写日志，
避免把 provider 返回、密钥配置等内部细节直接暴露到聊天界面。
"""


class AgentError(RuntimeError):
    code = "agent_unavailable"
    public_message = "时叙这会儿没接住，稍等一下再试。"

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.public_message)


class AgentConfigurationError(AgentError):
    code = "agent_not_configured"
    public_message = "时叙还没有完成模型配置，暂时不能回复。"


class AgentTimeoutError(AgentError):
    code = "agent_timeout"
    public_message = "时叙想得有点久，这句话先没等到回复。请再试一次。"


class AgentProviderError(AgentError):
    code = "agent_provider_error"
    public_message = "时叙暂时连不上回复服务，过一会儿再说。"


class AgentEmptyResponseError(AgentError):
    code = "agent_empty_response"
    public_message = "时叙刚刚没有生成完整回复，这句话我们再试一次。"

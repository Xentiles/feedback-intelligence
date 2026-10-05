namespace FeedbackIntelligence.Api.Workbench;

// Messages are app-owned; provider bodies, credentials and exception text stay private.
public sealed class ConnectionFailureException(string code, string message, bool reconnect = false) : InvalidOperationException(message)
{
    public string Code { get; } = code;
    public bool Reconnect { get; } = reconnect;
}

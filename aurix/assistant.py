"""Basic command handler for AURIX."""


def handle_command(command: str) -> str:
    """Acknowledge a recognized command.

    Actual AI reasoning and desktop actions will be implemented
    in later milestones.
    """
    cleaned_command = command.strip()

    if not cleaned_command:
        return "I'm listening. What do you need?"

    return (
        f"I heard your command: {cleaned_command}. "
        "Command execution will be added in a later milestone."
    )

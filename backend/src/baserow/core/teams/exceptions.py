class TeamDoesNotExist(Exception):
    """Raised when the requested team does not exist."""


class TeamNameNotUnique(Exception):
    """Raised when a team with the same name already exists in the workspace."""


class TeamMemberNotInWorkspace(Exception):
    """Raised when a user added to a team isn't a member of the team's workspace."""

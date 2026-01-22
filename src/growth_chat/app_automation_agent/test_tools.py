"""
Test script for individual tool testing.

This script tests each tool directly without using the full agent,
allowing for unit-style testing of tool functionality.
"""

from .tools import (CancelTeamInvitationTool, CreateTeamTool, DeleteTeamTool,
                    GetTeamInvitationsTool, GetTeamTool, InviteTeamMemberTool,
                    ListTeamsTool, RemoveTeamMemberTool, UpdateTeamMemberTool,
                    UpdateTeamTool)

_test_team_name = "Andre Test Team 1"
_test_team_description = "This is a test team 1"
_test_team_delete_id = 33
_test_team_update_id = 34
_test_team_invite_email = "andre@example.com"
_test_team_invite_role = "Builder"
_test_team_invitation_id = 9

def test_list_teams(auth_token: str):
    """Test listing teams."""
    print("\n" + "=" * 60)
    print("TEST: ListTeamsTool")
    print("=" * 60)
    
    tool = ListTeamsTool(auth_token=auth_token)
    result = tool._run_tool()
    print(f"Result:\n{result}")
    return result

def test_get_team(auth_token: str):
    """Test getting a team."""
    print("\n" + "=" * 60)
    print("TEST: GetTeamTool")
    print("=" * 60)
    
    tool = GetTeamTool(auth_token=auth_token)
    result = tool._run_tool(team_id=_test_team_update_id)
    print(f"Result:\n{result}")
    return result

def test_get_team_invitations(auth_token: str):
    """Test getting team invitations."""
    print("\n" + "=" * 60)
    print("TEST: GetTeamInvitationsTool")
    print("=" * 60)
    
    tool = GetTeamInvitationsTool(auth_token=auth_token)
    result = tool._run_tool(team_id=_test_team_update_id)
    print(f"Result:\n{result}")
    return result

def test_create_team(auth_token: str):
    """Test creating a team."""
    print("\n" + "=" * 60)
    print("TEST: CreateTeamTool")
    print("=" * 60)
    
    tool = CreateTeamTool(auth_token=auth_token)
    result = tool._run_tool(org_id=1, name=_test_team_name, description=_test_team_description)
    # save created team id as global variable
    print(f"Result:\n{result}")
    return result

def test_update_team(auth_token: str):
    """Test updating a team."""
    print("\n" + "=" * 60)
    print("TEST: UpdateTeamTool")
    print("=" * 60)
    
    tool = UpdateTeamTool(auth_token=auth_token)
    result = tool._run_tool(
        team_id=_test_team_update_id,
        name=_test_team_name + " Updated",
        description=_test_team_description + " updated"
    )
    print(f"Result:\n{result}")
    return result

def test_delete_team(auth_token: str):
    """Test deleting a team."""
    print("\n" + "=" * 60)
    print("TEST: DeleteTeamTool")
    print("=" * 60)
    
    tool = DeleteTeamTool(auth_token=auth_token)
    result = tool._run_tool(team_id=_test_team_delete_id)
    print(f"Result:\n{result}")
    return result

def test_invite_team_member(auth_token: str):
    """Test inviting a team member."""
    print("\n" + "=" * 60)
    print("TEST: InviteTeamMemberTool")
    print("=" * 60)
    
    tool = InviteTeamMemberTool(auth_token=auth_token)
    result = tool._run_tool(team_id=_test_team_update_id, email=_test_team_invite_email, role=_test_team_invite_role)
    print(f"Result:\n{result}")
    return result

def test_update_team_member(auth_token: str):
    """Test updating a team member."""
    print("\n" + "=" * 60)
    print("TEST: UpdateTeamMemberTool")
    print("=" * 60)
    
    tool = UpdateTeamMemberTool(auth_token=auth_token)
    result = tool._run_tool(team_id=_test_team_update_id, member_id=_test_team_invite_email, role="Admin")
    print(f"Result:\n{result}")
    return result

def test_remove_team_member(auth_token: str):
    """Test removing a team member."""
    print("\n" + "=" * 60)
    print("TEST: RemoveTeamMemberTool")
    print("=" * 60)
    
    tool = RemoveTeamMemberTool(auth_token=auth_token)
    result = tool._run_tool(team_id=13, member_id=21)
    print(f"Result:\n{result}")
    return result

def test_cancel_team_invitation(auth_token: str):
    """Test canceling a team invitation."""
    print("\n" + "=" * 60)
    print("TEST: CancelTeamInvitationTool")
    print("=" * 60)
    
    tool = CancelTeamInvitationTool(auth_token=auth_token)
    result = tool._run_tool(team_id=_test_team_update_id, invitation_id=_test_team_invitation_id)
    print(f"Result:\n{result}")
    return result

if __name__ == "__main__":
    auth_token = input("Enter your auth token: ")

    test_list_teams(auth_token)
    test_get_team(auth_token)
    test_get_team_invitations(auth_token)
    # test_delete_team(auth_token)
    # test_create_team(auth_token)
    # test_update_team(auth_token)
    # test_cancel_team_invitation(auth_token)
    # test_invite_team_member(auth_token)
    # test_remove_team_member(auth_token)
    # test_update_team_member(auth_token)
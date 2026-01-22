# User overlay chain for personalized recommendations
import logging
import re
from typing import Dict, Any, Optional
from src.data_models.analysis_schemas import BaseAnalysisArtifact, UserRecommendation
from src.agent.delegate.llm_provider import LLMManager

logger = logging.getLogger(__name__)

class UserOverlayChain:
    """Generates personalized recommendations using base analysis + user preferences"""
    
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.max_retries = 1  # Allow one retry for validation failures
    
    async def generate_personalized_recommendation(self, 
                                                  base_analysis: BaseAnalysisArtifact, 
                                                  user_preferences: Optional[Dict[str, Any]] = None) -> UserRecommendation:
        """Generate personalized justification and voting decision"""
        
        logger.info(f"🎯 Generating personalized recommendation for proposal {base_analysis.proposal_id}")
        
        try:
            # Build personalized prompt
            prompt = self._build_overlay_prompt(base_analysis, user_preferences)
            
            # Generate response
            for attempt in range(self.max_retries + 1):
                try:
                    response = self.llm.generate_from_prompt(prompt)
                    
                    # Parse and validate output
                    result = self._parse_overlay_response(response, base_analysis.voting_options)
                    
                    # Create recommendation object
                    recommendation = UserRecommendation(
                        justification=result["justification"],
                        voting_decision=result["voting_decision"],
                        is_actionable=base_analysis.is_proposal_active(),
                        artifact_version=base_analysis.version
                    )
                    
                    # Validate against voting options
                    recommendation.validate_against_options(base_analysis.voting_options)
                    
                    logger.info(f"✅ Generated personalized recommendation: {result['voting_decision']}")
                    return recommendation
                    
                except ValueError as e:
                    if attempt < self.max_retries:
                        logger.warning(f"Validation failed (attempt {attempt + 1}), retrying: {e}")
                        # Make prompt stricter for retry
                        prompt = self._build_strict_overlay_prompt(base_analysis, user_preferences, str(e))
                        continue
                    else:
                        logger.error(f"Failed validation after {self.max_retries + 1} attempts: {e}")
                        raise
            
        except Exception as e:
            logger.error(f"❌ Failed to generate personalized recommendation: {str(e)}")
            # Return safe fallback recommendation
            return self._create_fallback_recommendation(base_analysis, str(e))
    
    def _build_overlay_prompt(self, analysis: BaseAnalysisArtifact, preferences: Optional[Dict[str, Any]] = None) -> str:
        """Build prompt that combines analysis with user preferences"""
        
        # Build preference emphasis
        preference_emphasis = self._build_preference_emphasis(preferences) if preferences else ""
        
        # Handle closed proposals
        proposal_status_note = ""
        if not analysis.is_proposal_active():
            proposal_status_note = "\n⚠️ NOTE: This proposal is CLOSED/COMPLETED. Your recommendation should be marked as historical/non-actionable and include a note about this being a closed proposal.\n"
        
        # Build arguments summary (enhanced with extracted arguments)
        enhanced_for_args = analysis.extracted_arguments.get("for", []) or analysis.key_arguments.get("for", [])
        enhanced_against_args = analysis.extracted_arguments.get("against", []) or analysis.key_arguments.get("against", [])
        
        for_args = "; ".join(enhanced_for_args) or "No specific arguments for found"
        against_args = "; ".join(enhanced_against_args) or "No specific arguments against found"
        
        # Build perspective insights summary
        perspective_summary = self._build_perspective_summary(analysis)
        
        prompt = f"""Based on the comprehensive analysis below, provide a personalized voting recommendation.

{proposal_status_note}

## Proposal Analysis Summary:
**Proposal:** {analysis.clean_proposal_summary or analysis.proposal_summary}
**Status:** {analysis.proposal_status}
**Category:** {analysis.proposal_category} | **Complexity:** {analysis.proposal_complexity} | **Urgency:** {analysis.urgency_level}
**Arguments For:** {for_args}
**Arguments Against:** {against_args}
**Financial Impact:** {analysis.financial_impact or 'Not specified'}

{perspective_summary}
**Similar Proposals Found:** {len(analysis.similar_proposals)}
**Preliminary Insights:** {analysis.preliminary_insights}

## Available Voting Options (choose EXACTLY one):
{self._format_voting_options(analysis.voting_options)}

{preference_emphasis}

## Instructions:
Provide your recommendation in this EXACT format:
Justification: [Your detailed reasoning focusing on the most important factors{' and user preferences' if preferences else ''}]
Final Vote: [Choose EXACTLY one option from the voting options above - copy it exactly as written]

## Critical Requirements:
1. Your "Final Vote" MUST be one of the exact options listed above
2. Do NOT modify the option text or combine multiple options
3. Do NOT use commas or list multiple options
4. Your justification should be clear and substantive (at least 50 words)
{f"5. IMPORTANT: This proposal is {analysis.proposal_status.upper()} - you MUST mention this is a closed/historical proposal in your justification" if not analysis.is_proposal_active() else ""}

Begin your response:"""

        return prompt
    
    def _build_strict_overlay_prompt(self, analysis: BaseAnalysisArtifact, preferences: Optional[Dict[str, Any]], error_msg: str) -> str:
        """Build stricter prompt after validation failure"""
        
        options_list = "\n".join([f"- {option}" for option in analysis.voting_options])
        
        return f"""VALIDATION ERROR OCCURRED: {error_msg}

You must provide a recommendation that follows the format exactly.

## Available Options (choose ONE):
{options_list}

## Proposal Summary:
{analysis.proposal_summary}

## Your Task:
Provide ONLY this format:
Justification: [Your reasoning in at least 50 words]
Final Vote: [Copy ONE option exactly from the list above]

## Example:
Justification: Based on the analysis, this proposal addresses important governance needs and has strong community support. The financial impact appears manageable and aligns with the DAO's strategic objectives.
Final Vote: For

Now provide your response:"""
    
    def _build_preference_emphasis(self, preferences: Dict[str, Any]) -> str:
        """Build preference-based emphasis for the prompt with enhanced mapping for rich user preference data"""
        if not preferences:
            return ""
        
        emphasis_parts = []
        
        # Map riskTolerance (0-100 scale from frontend)
        risk_tolerance = preferences.get('riskTolerance', 50)
        if isinstance(risk_tolerance, (int, float)):
            if risk_tolerance < 30:
                emphasis_parts.append("Focus on risk mitigation and conservative approaches")
            elif risk_tolerance > 70:
                emphasis_parts.append("Consider innovative approaches and calculated risks")
        
        # Map decentralizationImportance (0-100 scale from frontend)
        decentralization = preferences.get('decentralizationImportance', 50)
        if isinstance(decentralization, (int, float)):
            if decentralization > 70:
                emphasis_parts.append("Emphasize decentralization and community governance aspects")
            elif decentralization < 30:
                emphasis_parts.append("Focus on operational efficiency and practical outcomes")
        
        # Map treasuryManagement stance
        treasury_mgmt = preferences.get('treasuryManagement', 'moderate')
        if treasury_mgmt == 'conservative':
            emphasis_parts.append("Favor proposals that maintain financial stability and minimize treasury risk")
        elif treasury_mgmt == 'aggressive':
            emphasis_parts.append("Support proposals that enable growth even with higher financial risk")
        
        # Map governancePriorities array
        priorities = preferences.get('governancePriorities', [])
        if isinstance(priorities, list):
            if 'security' in priorities:
                emphasis_parts.append("Prioritize protocol security and risk management aspects")
            if 'economics' in priorities:
                emphasis_parts.append("Focus on economic sustainability and tokenomics")
            if 'community' in priorities:
                emphasis_parts.append("Consider community impact and engagement")
            if 'innovation' in priorities:
                emphasis_parts.append("Value technical innovation and new features")
        
        # Map delegatePersonality array
        personalities = preferences.get('delegatePersonality', [])
        if isinstance(personalities, list):
            if 'conservative' in personalities:
                emphasis_parts.append("Take a cautious, well-researched approach to recommendations")
            elif 'progressive' in personalities:
                emphasis_parts.append("Be open to innovative and forward-thinking proposals")
        
        # Map stance preferences
        stances = []
        if preferences.get('feeChangeStance') == 'conservative':
            stances.append("be cautious about fee changes")
        if preferences.get('protocolUpgradeStance') == 'conservative':
            stances.append("be careful with protocol upgrades")  
        if preferences.get('grantsFundingStance') == 'conservative':
            stances.append("be selective with grant funding")
        
        if stances:
            emphasis_parts.append(f"Generally {', '.join(stances)}")
        
        # Add custom instructions if present
        custom_instructions = preferences.get('customInstructions', '').strip()
        if custom_instructions:
            emphasis_parts.append(f"Follow these custom instructions: {custom_instructions}")
        
        # Legacy preference mapping for backward compatibility
        if preferences.get('risk_tolerance') == 'low':
            emphasis_parts.append("Focus on risk mitigation and conservative approaches")
        elif preferences.get('risk_tolerance') == 'high':
            emphasis_parts.append("Consider innovative approaches and calculated risks")
        
        if preferences.get('governance_priority') == 'decentralization':
            emphasis_parts.append("Emphasize decentralization and community governance aspects")
        elif preferences.get('governance_priority') == 'efficiency':
            emphasis_parts.append("Focus on operational efficiency and practical outcomes")
        
        if preferences.get('financial_priority') == 'growth':
            emphasis_parts.append("Prioritize proposals that support long-term growth")
        elif preferences.get('financial_priority') == 'stability':
            emphasis_parts.append("Favor proposals that maintain financial stability")
        
        if preferences.get('community_focus') == 'high':
            emphasis_parts.append("Consider community impact and engagement")
        
        if emphasis_parts:
            return f"\n## User Preferences (emphasize these aspects):\n" + "\n".join([f"- {part}" for part in emphasis_parts]) + "\n"
        
        return "\n## User Preferences: Consider user's individual priorities in your recommendation.\n"
    
    def _format_voting_options(self, voting_options: list) -> str:
        """Format voting options clearly"""
        return "\n".join([f"• {option}" for option in voting_options])
    
    def _parse_overlay_response(self, response: str, voting_options: list) -> Dict[str, str]:
        """Parse and validate overlay response"""
        
        # Extract justification and final vote using regex
        justification_match = re.search(r"Justification:\s*(.+?)(?=Final Vote:|$)", response, re.DOTALL | re.IGNORECASE)
        vote_match = re.search(r"Final Vote:\s*(.+)", response, re.IGNORECASE)
        
        if not justification_match:
            raise ValueError("Could not find 'Justification:' in response")
        
        if not vote_match:
            raise ValueError("Could not find 'Final Vote:' in response")
        
        justification = justification_match.group(1).strip()
        voting_decision = vote_match.group(1).strip()
        
        # Clean up voting decision (remove extra text after the option)
        voting_decision = self._clean_voting_decision(voting_decision, voting_options)
        
        # Validate justification
        if len(justification) < 20:
            raise ValueError(f"Justification too short ({len(justification)} chars): {justification}")
        
        # Validate voting decision
        if voting_decision not in voting_options:
            # Try case-insensitive match
            matched_option = None
            for option in voting_options:
                if voting_decision.lower() == option.lower():
                    matched_option = option
                    break
            
            if matched_option:
                voting_decision = matched_option
            else:
                raise ValueError(f"Voting decision '{voting_decision}' not in allowed options: {voting_options}")
        
        return {
            "justification": justification,
            "voting_decision": voting_decision
        }
    
    def _clean_voting_decision(self, raw_decision: str, voting_options: list) -> str:
        """Clean up voting decision text to match exact options"""
        
        # Remove common extra text
        raw_decision = raw_decision.strip()
        
        # Remove everything after newline or period
        raw_decision = raw_decision.split('\n')[0].split('.')[0].strip()
        
        # Check for exact match first
        if raw_decision in voting_options:
            return raw_decision
        
        # Look for the option within the text
        for option in voting_options:
            if option.lower() in raw_decision.lower():
                return option
        
        return raw_decision
    
    def _build_perspective_summary(self, analysis: BaseAnalysisArtifact) -> str:
        """Build summary of multi-perspective analysis for user overlay"""
        
        if not analysis.perspective_analyses:
            return "## Multi-Perspective Analysis:\n*No perspective analysis available*\n"
        
        summary_parts = ["## Multi-Perspective Analysis:"]
        
        # Add consensus information
        if analysis.perspective_consensus != "unknown":
            consensus_text = f"**Consensus:** {analysis.perspective_consensus}"
            if analysis.dominant_perspective:
                consensus_text += f" (strongest case: {analysis.dominant_perspective})"
            summary_parts.append(consensus_text)
        
        # Add each perspective's key insights
        for perspective_data in analysis.perspective_analyses:
            perspective = perspective_data.get('perspective', 'unknown').title()
            tendency = perspective_data.get('recommendation_tendency', 'neutral')
            concerns = perspective_data.get('key_concerns', [])
            benefits = perspective_data.get('key_benefits', [])
            confidence = perspective_data.get('confidence', 0)
            
            perspective_summary = f"**{perspective}:** {tendency} (confidence: {confidence}/10)"
            
            if concerns:
                perspective_summary += f" | Concerns: {', '.join(concerns[:2])}"
            if benefits:
                perspective_summary += f" | Benefits: {', '.join(benefits[:2])}"
            
            summary_parts.append(perspective_summary)
        
        # Add synthesis if available
        if analysis.synthesis_insights:
            summary_parts.append(f"**Synthesis:** {analysis.synthesis_insights[:150]}...")
        
        return "\n".join(summary_parts) + "\n"
    
    def _create_fallback_recommendation(self, analysis: BaseAnalysisArtifact, error_msg: str) -> UserRecommendation:
        """Create safe fallback recommendation when generation fails"""
        
        # Choose a safe default option (prefer Abstain if available)
        safe_option = "Abstain"
        if safe_option not in analysis.voting_options:
            # Use first available option
            safe_option = analysis.voting_options[0] if analysis.voting_options else "Abstain"
        
        fallback_justification = (f"Unable to generate personalized recommendation due to technical error. "
                                f"Based on the base analysis, this proposal involves {analysis.proposal_summary}. "
                                f"Recommending {safe_option} pending manual review. Error: {error_msg}")
        
        if not analysis.is_proposal_active():
            fallback_justification += " Note: This proposal is closed and this recommendation is historical only."
        
        return UserRecommendation(
            justification=fallback_justification,
            voting_decision=safe_option,
            is_actionable=analysis.is_proposal_active(),
            artifact_version=analysis.version
        )

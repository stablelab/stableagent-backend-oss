# Wrapper for existing ReasoningAgent to produce structured artifacts
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from src.agent.delegate.reasoning_agent import ReasoningAgent
from src.data_models.analysis_schemas import BaseAnalysisArtifact
from src.agent.multi_perspective import (
    MultiPerspectiveAnalyzer,
    ParsedInput,
    SimpleTextParser,
)

logger = logging.getLogger(__name__)


class DelegateLLMAdapter:
    """Adapter to make delegate LLMManager compatible with multi_perspective LLM Protocol."""
    
    def __init__(self, llm_manager):
        """
        Initialize the adapter.
        
        Args:
            llm_manager: Delegate LLMManager instance
        """
        self.llm_manager = llm_manager
    
    def generate_from_prompt(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt using LLMManager."""
        return self.llm_manager.generate_from_prompt(prompt, **kwargs)

class BaseAnalysisWrapper:
    """Wraps existing ReasoningAgent to produce structured BaseAnalysisArtifact"""
    
    def __init__(self, reasoning_agent: ReasoningAgent):
        self.reasoning_agent = reasoning_agent
    
    def generate_base_analysis(self, proposal_id: str, dao_id: str = None, source: str = None) -> BaseAnalysisArtifact:
        """Generate base analysis artifact using existing ReasoningAgent"""
        
        logger.info(f"🔧 Generating base analysis artifact for proposal {proposal_id}")
        
        try:
            # Use existing ReasoningAgent to get raw analysis
            raw_result = self.reasoning_agent.analyze_with_reasoning(
                proposal_id=proposal_id,
                dao_id=dao_id,
                source=source
            )
            
            # Check for errors in raw result
            if 'error' in raw_result:
                raise RuntimeError(f"Base analysis failed: {raw_result['error']}")
            
            # Convert raw result to structured artifact
            artifact = self._convert_to_artifact(raw_result, proposal_id, dao_id, source)
            
            # Validate the artifact
            artifact.validate_required_fields()
            
            logger.info(f"Generated base analysis artifact for {proposal_id}")
            return artifact
            
        except Exception as e:
            logger.error(f"Failed to generate base analysis for {proposal_id}: {str(e)}")
            raise
    
    def _convert_to_artifact(self, raw_result: Dict[str, Any], proposal_id: str, dao_id: str, source: str) -> BaseAnalysisArtifact:
        """Convert raw ReasoningAgent output to BaseAnalysisArtifact"""
        
        # Extract basic info
        detected_source = raw_result.get('source', source)
        detected_dao_id = raw_result.get('dao_id', dao_id)
        voting_options = raw_result.get('voting_options', [])
        
        # Extract reasoning trace and analysis content
        trace = raw_result.get('trace', [])
        analysis_text = raw_result.get('analysis', '')
        reasoning_text = raw_result.get('reasoning', '')
        
        # Build proposal summary from analysis
        proposal_summary = self._extract_proposal_summary(analysis_text, reasoning_text)
        
        # Extract key arguments from trace and analysis
        key_arguments = self._extract_key_arguments(trace, analysis_text)
        
        # Determine proposal status
        proposal_status = self._determine_proposal_status(raw_result, trace)
        
        # Extract similar proposals info
        similar_proposals = self._extract_similar_proposals(raw_result, trace)
        
        # Extract references and data sources
        references = self._extract_references(trace)
        data_sources_used = self._extract_data_sources(raw_result, trace)
        
        # Extract financial impact and voter stats if available
        financial_impact = self._extract_financial_impact(analysis_text, trace)
        voter_stats = self._extract_voter_stats(raw_result)
        
        # Extract timeline information
        timeline_info = self._extract_timeline_info(raw_result, trace)
        
        # Build preliminary insights
        preliminary_insights = self._build_preliminary_insights(raw_result, trace)
        
        # Enhanced data extraction
        clean_summary = self._extract_clean_summary(raw_result, trace)
        extracted_arguments = self._extract_structured_arguments(raw_result, trace)
        react_steps = self._extract_react_steps(trace)
        final_reasoning = self._extract_final_reasoning(trace)
        stakeholders = self._extract_stakeholders(raw_result, trace)
        risk_factors = self._extract_risk_factors(raw_result, trace)
        opportunity_factors = self._extract_opportunity_factors(raw_result, trace)
        governance_implications = self._extract_governance_implications(raw_result, trace)
        economic_implications = self._extract_economic_implications(raw_result, trace)
        categorization = self._categorize_proposal(clean_summary, extracted_arguments)
        
        # C) Multi-Delegate Perspective Analysis (NEW!)
        perspective_data = self._analyze_multiple_perspectives(
            clean_summary, extracted_arguments, risk_factors, 
            opportunity_factors, governance_implications, economic_implications
        )
        
        # Create the artifact
        artifact = BaseAnalysisArtifact(
            proposal_id=proposal_id,
            dao_id=detected_dao_id or dao_id or "",
            source=detected_source,
            analyzed_at=datetime.now(timezone.utc),
            
            # Core information
            proposal_summary=proposal_summary,
            proposal_status=proposal_status,
            voting_options=voting_options,
            
            # Analysis content
            key_arguments=key_arguments,
            financial_impact=financial_impact,
            voter_stats=voter_stats,
            timeline_info=timeline_info,
            similar_proposals=similar_proposals,
            references=references,
            
            # Metadata
            data_sources_used=data_sources_used,
            embedding_generated=self._check_embedding_generated(raw_result),
            reasoning_trace=trace,
            preliminary_insights=preliminary_insights,
            
            # Enhanced fields for multi-perspective analysis
            clean_proposal_summary=clean_summary,
            extracted_arguments=extracted_arguments,
            key_stakeholders=stakeholders,
            risk_factors=risk_factors,
            opportunity_factors=opportunity_factors,
            governance_implications=governance_implications,
            economic_implications=economic_implications,
            react_steps=react_steps,
            final_reasoning=final_reasoning,
            proposal_complexity=categorization.get("complexity", "medium"),
            proposal_category=categorization.get("category", "governance"),
            urgency_level=categorization.get("urgency", "normal"),
            
            # Multi-perspective analysis fields
            perspective_analyses=perspective_data.get("analyses", []),
            synthesis_insights=perspective_data.get("synthesis", ""),
            perspectives_analyzed=perspective_data.get("perspectives_analyzed", []),
            perspective_consensus=perspective_data.get("consensus", "unknown"),
            dominant_perspective=perspective_data.get("dominant_perspective", "")
        )
        
        return artifact
    
    def _extract_proposal_summary(self, analysis_text: str, reasoning_text: str) -> str:
        """Extract proposal summary from analysis text"""
        # Look for summary in reasoning trace or create from analysis
        if analysis_text:
            # Take first few sentences as summary
            sentences = analysis_text.split('. ')
            if len(sentences) >= 2:
                return '. '.join(sentences[:2]) + '.'
            return analysis_text[:200] + '...' if len(analysis_text) > 200 else analysis_text
        
        if reasoning_text:
            return reasoning_text[:200] + '...' if len(reasoning_text) > 200 else reasoning_text
        
        return "Proposal analysis completed."
    
    def _extract_key_arguments(self, trace: list, analysis_text: str) -> Dict[str, list]:
        """Extract key arguments for and against from trace and analysis"""
        arguments = {"for": [], "against": []}
        
        # Look through trace for arguments
        for step in trace:
            if step.get('output'):
                output = step['output'].lower()
                if 'support' in output or 'benefit' in output or 'positive' in output:
                    # Extract argument for
                    arg = self._extract_argument_from_text(step['output'], 'for')
                    if arg and arg not in arguments['for']:
                        arguments['for'].append(arg)
                
                if 'concern' in output or 'risk' in output or 'negative' in output or 'against' in output:
                    # Extract argument against
                    arg = self._extract_argument_from_text(step['output'], 'against')
                    if arg and arg not in arguments['against']:
                        arguments['against'].append(arg)
        
        # Fallback: extract from analysis text
        if not arguments['for'] and not arguments['against'] and analysis_text:
            if 'recommend' in analysis_text.lower() and 'support' in analysis_text.lower():
                arguments['for'].append("Analysis recommends support based on proposal benefits")
            elif 'concern' in analysis_text.lower() or 'risk' in analysis_text.lower():
                arguments['against'].append("Analysis identifies concerns or risks")
        
        return arguments
    
    def _extract_argument_from_text(self, text: str, sentiment: str) -> str:
        """Extract a specific argument from text"""
        # Simple extraction - take the sentence containing key words
        sentences = text.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10 and len(sentence) < 150:  # Reasonable length
                if sentiment == 'for' and any(word in sentence.lower() for word in ['support', 'benefit', 'positive', 'advantage']):
                    return sentence
                elif sentiment == 'against' and any(word in sentence.lower() for word in ['concern', 'risk', 'negative', 'problem']):
                    return sentence
        return ""
    
    def _determine_proposal_status(self, raw_result: Dict[str, Any], trace: list) -> str:
        """Determine proposal status from available data"""
        # Look for status indicators in the raw result or trace
        for step in trace:
            if step.get('output'):
                output = step['output'].lower()
                if 'active' in output or 'voting' in output:
                    return 'active'
                elif 'closed' in output or 'ended' in output or 'completed' in output:
                    return 'closed'
                elif 'pending' in output or 'upcoming' in output:
                    return 'pending'
        
        # Default assumption - if we can analyze it, it's likely active or recently closed
        return 'active'
    
    def _extract_similar_proposals(self, raw_result: Dict[str, Any], trace: list) -> list:
        """Extract information about similar proposals"""
        similar_proposals = []
        
        # Look for similar content count
        similar_content_count = raw_result.get('similar_content_count', {})
        if similar_content_count.get('proposals', 0) > 0:
            similar_proposals.append({
                'count': similar_content_count['proposals'],
                'source': 'embedding_similarity',
                'note': f"Found {similar_content_count['proposals']} similar proposals via embedding search"
            })
        
        return similar_proposals
    
    def _extract_references(self, trace: list) -> list:
        """Extract references and citations from trace"""
        references = []
        
        for step in trace:
            if step.get('observation') and 'http' in str(step['observation']):
                # Extract URLs from observations
                import re
                urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 
                                str(step['observation']))
                references.extend(urls)
        
        return list(set(references))  # Remove duplicates
    
    def _extract_data_sources(self, raw_result: Dict[str, Any], trace: list) -> list:
        """Extract list of data sources used"""
        sources = []
        
        # Add source from raw result
        if raw_result.get('source'):
            sources.append(raw_result['source'])
        
        # Look for data source indicators in trace
        for step in trace:
            if step.get('action'):
                action = step['action'].lower()
                if 'search' in action:
                    sources.append('historical_search')
                elif 'discussion' in action:
                    sources.append('forum_discussions')
                elif 'proposal' in action:
                    sources.append('proposal_content')
        
        # Add embedding if similar content was found
        similar_content_count = raw_result.get('similar_content_count', {})
        if similar_content_count.get('proposals', 0) > 0 or similar_content_count.get('discussions', 0) > 0:
            sources.append('embedding_similarity')
        
        return list(set(sources))
    
    def _extract_financial_impact(self, analysis_text: str, trace: list) -> str:
        """Extract financial impact information if available"""
        # Look for financial keywords in analysis
        if analysis_text:
            financial_keywords = ['cost', 'fund', 'budget', 'treasury', 'token', 'price', 'economic', 'financial']
            if any(keyword in analysis_text.lower() for keyword in financial_keywords):
                # Extract relevant sentence
                sentences = analysis_text.split('.')
                for sentence in sentences:
                    if any(keyword in sentence.lower() for keyword in financial_keywords):
                        return sentence.strip()
        
        return None
    
    def _extract_voter_stats(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract voter statistics if available"""
        # This would depend on what data is available in raw_result
        # For now, return None as this info might not be readily available
        return None
    
    def _extract_timeline_info(self, raw_result: Dict[str, Any], trace: list) -> Dict[str, Any]:
        """Extract timeline information"""
        timeline = {}
        
        # Look for timeline info in trace
        for step in trace:
            if step.get('output'):
                output = step['output']
                # Look for date/time patterns
                import re
                dates = re.findall(r'\d{4}-\d{2}-\d{2}', output)
                if dates:
                    timeline['dates_mentioned'] = dates
        
        timeline['analysis_completed_at'] = datetime.now(timezone.utc).isoformat()
        return timeline
    
    def _build_preliminary_insights(self, raw_result: Dict[str, Any], trace: list) -> str:
        """Build preliminary insights from the analysis"""
        insights = []
        
        # Add insight about similar content
        similar_content_count = raw_result.get('similar_content_count', {})
        if similar_content_count.get('proposals', 0) > 0:
            insights.append(f"Found {similar_content_count['proposals']} similar historical proposals")
        
        if similar_content_count.get('discussions', 0) > 0:
            insights.append(f"Found {similar_content_count['discussions']} related discussions")
        
        # Add insight about reasoning steps
        if trace:
            insights.append(f"Completed {len(trace)} reasoning steps")
        
        # Add insight about voting options
        voting_options = raw_result.get('voting_options', [])
        if voting_options:
            insights.append(f"Available voting options: {', '.join(voting_options)}")
        
        return '; '.join(insights) if insights else "Base analysis completed successfully"
    
    def _check_embedding_generated(self, raw_result: Dict[str, Any]) -> bool:
        """Check if embedding was generated during analysis"""
        # Look for embedding-related indicators
        similar_content_count = raw_result.get('similar_content_count', {})
        return (similar_content_count.get('proposals', 0) > 0 or 
                similar_content_count.get('discussions', 0) > 0)
    
    # ========== Enhanced Data Extraction Methods for Multi-Perspective Analysis ==========
    
    def _extract_clean_summary(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> str:
        """Extract clean proposal summary without ReAct formatting"""
        # Look for SummarizeProposal action in trace
        for step in trace:
            if step.get('action') == 'SummarizeProposal':
                observation = step.get('observation', '')
                if observation:
                    # Clean up the observation text
                    clean_text = observation.replace('Action: SummarizeProposal\n', '')
                    clean_text = clean_text.replace('Observation: ', '')
                    clean_text = clean_text.strip()
                    return clean_text
        
        # Fallback to analysis text
        analysis_text = raw_result.get('justification', '')
        if analysis_text:
            # Take first 200 words as summary
            words = analysis_text.split()[:200]
            return ' '.join(words) + ('...' if len(words) == 200 else '')
        
        return "No summary available"
    
    def _extract_structured_arguments(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Extract clean arguments from ReAct reasoning"""
        arguments = {"for": [], "against": []}
        
        # Parse through ReAct steps to find arguments
        for step in trace:
            action = step.get('action', '')
            observation = step.get('observation', '')
            thought = step.get('thought', '')
            
            # Look for arguments in LookupDiscussion
            if action == 'LookupDiscussion' and observation:
                # Extract positive arguments
                if 'support' in observation.lower() or 'favor' in observation.lower():
                    positive_phrases = self._extract_argument_phrases(observation, positive=True)
                    arguments['for'].extend(positive_phrases)
                
                # Extract negative arguments
                if 'concern' in observation.lower() or 'critic' in observation.lower() or 'against' in observation.lower():
                    negative_phrases = self._extract_argument_phrases(observation, positive=False)
                    arguments['against'].extend(negative_phrases)
            
            # Look for arguments in SearchHistory
            if action == 'SearchHistory' and observation:
                if 'criticized' in observation.lower() or 'concern' in observation.lower():
                    concerns = self._extract_argument_phrases(observation, positive=False)
                    arguments['against'].extend(concerns)
                
                if 'successful' in observation.lower() or 'positive' in observation.lower():
                    positives = self._extract_argument_phrases(observation, positive=True)
                    arguments['for'].extend(positives)
        
        # Clean up and deduplicate
        arguments['for'] = list(set([arg.strip() for arg in arguments['for'] if arg.strip()]))
        arguments['against'] = list(set([arg.strip() for arg in arguments['against'] if arg.strip()]))
        
        return arguments
    
    def _extract_argument_phrases(self, text: str, positive: bool = True) -> List[str]:
        """Extract argument phrases from text"""
        phrases = []
        sentences = text.split('.')
        
        if positive:
            keywords = ['support', 'favor', 'positive', 'benefit', 'advantage', 'good', 'necessary']
        else:
            keywords = ['concern', 'critic', 'against', 'risk', 'problem', 'issue', 'worry']
        
        for sentence in sentences:
            sentence = sentence.strip()
            if any(keyword in sentence.lower() for keyword in keywords):
                if len(sentence) > 20 and len(sentence) < 150:  # Reasonable length
                    phrases.append(sentence)
        
        return phrases[:3]  # Limit to 3 phrases per category
    
    def _extract_react_steps(self, trace: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extract structured ReAct steps"""
        steps = []
        for i, step in enumerate(trace, 1):
            step_data = {
                'step_number': str(i),
                'action': step.get('action', ''),
                'thought': step.get('thought', ''),
                'observation': step.get('observation', '')
            }
            steps.append(step_data)
        return steps
    
    def _extract_final_reasoning(self, trace: List[Dict[str, Any]]) -> str:
        """Extract the final reasoning from ReAct trace"""
        # Look for Final Thought or final step
        for step in reversed(trace):
            thought = step.get('thought', '')
            if 'final' in thought.lower() or len(thought) > 100:
                return thought
        
        # Fallback to last thought
        if trace:
            return trace[-1].get('thought', 'No final reasoning available')
        
        return "No final reasoning available"
    
    def _extract_stakeholders(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
        """Extract key stakeholders mentioned in the analysis"""
        stakeholders = set()
        
        # Common stakeholders to look for
        stakeholder_keywords = [
            'community', 'delegates', 'token holders', 'users', 'developers', 
            'treasury', 'dao', 'governance', 'voters', 'participants'
        ]
        
        # Search through all text
        all_text = raw_result.get('justification', '') + ' '.join([
            step.get('observation', '') + ' ' + step.get('thought', '') 
            for step in trace
        ])
        
        all_text_lower = all_text.lower()
        for keyword in stakeholder_keywords:
            if keyword in all_text_lower:
                stakeholders.add(keyword.title())
        
        return list(stakeholders)[:5]  # Limit to 5 stakeholders
    
    def _extract_risk_factors(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
        """Extract risk factors from the analysis"""
        risks = []
        
        # Search for risk-related terms
        risk_keywords = ['risk', 'concern', 'problem', 'issue', 'challenge', 'threat', 'danger']
        
        for step in trace:
            observation = step.get('observation', '')
            thought = step.get('thought', '')
            
            for text in [observation, thought]:
                if any(keyword in text.lower() for keyword in risk_keywords):
                    # Extract sentences containing risk terms
                    sentences = text.split('.')
                    for sentence in sentences:
                        if any(keyword in sentence.lower() for keyword in risk_keywords):
                            clean_sentence = sentence.strip()
                            if 20 < len(clean_sentence) < 120:
                                risks.append(clean_sentence)
        
        return list(set(risks))[:4]  # Limit to 4 unique risks
    
    def _extract_opportunity_factors(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
        """Extract opportunity factors from the analysis"""
        opportunities = []
        
        # Search for opportunity-related terms
        opp_keywords = ['opportunity', 'benefit', 'advantage', 'improvement', 'enhance', 'increase', 'optimize']
        
        for step in trace:
            observation = step.get('observation', '')
            thought = step.get('thought', '')
            
            for text in [observation, thought]:
                if any(keyword in text.lower() for keyword in opp_keywords):
                    sentences = text.split('.')
                    for sentence in sentences:
                        if any(keyword in sentence.lower() for keyword in opp_keywords):
                            clean_sentence = sentence.strip()
                            if 20 < len(clean_sentence) < 120:
                                opportunities.append(clean_sentence)
        
        return list(set(opportunities))[:4]  # Limit to 4 unique opportunities
    
    def _extract_governance_implications(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
        """Extract governance implications from the analysis"""
        implications = []
        
        gov_keywords = ['governance', 'voting', 'decision', 'delegate', 'power', 'participation', 'quorum']
        
        for step in trace:
            observation = step.get('observation', '')
            if any(keyword in observation.lower() for keyword in gov_keywords):
                sentences = observation.split('.')
                for sentence in sentences:
                    if any(keyword in sentence.lower() for keyword in gov_keywords):
                        clean_sentence = sentence.strip()
                        if 20 < len(clean_sentence) < 120:
                            implications.append(clean_sentence)
        
        return list(set(implications))[:3]  # Limit to 3 implications
    
    def _extract_economic_implications(self, raw_result: Dict[str, Any], trace: List[Dict[str, Any]]) -> List[str]:
        """Extract economic implications from the analysis"""
        implications = []
        
        econ_keywords = ['treasury', 'fund', 'token', 'economic', 'financial', 'cost', 'budget', 'allocation']
        
        for step in trace:
            observation = step.get('observation', '')
            if any(keyword in observation.lower() for keyword in econ_keywords):
                sentences = observation.split('.')
                for sentence in sentences:
                    if any(keyword in sentence.lower() for keyword in econ_keywords):
                        clean_sentence = sentence.strip()
                        if 20 < len(clean_sentence) < 120:
                            implications.append(clean_sentence)
        
        return list(set(implications))[:3]  # Limit to 3 implications
    
    def _categorize_proposal(self, summary: str, arguments: Dict[str, List[str]]) -> Dict[str, str]:
        """Categorize proposal for perspective analysis"""
        summary_lower = summary.lower()
        
        # Determine complexity
        complexity = "medium"  # default
        if len(summary.split()) > 150 or len(arguments.get('for', [])) + len(arguments.get('against', [])) > 6:
            complexity = "complex"
        elif len(summary.split()) < 50:
            complexity = "simple"
        
        # Determine category
        category = "governance"  # default
        if any(word in summary_lower for word in ['treasury', 'fund', 'token', 'budget']):
            category = "treasury"
        elif any(word in summary_lower for word in ['protocol', 'technical', 'upgrade', 'smart contract']):
            category = "protocol"
        elif any(word in summary_lower for word in ['delegate', 'voting', 'governance', 'quorum']):
            category = "governance"
        
        # Determine urgency
        urgency = "normal"  # default
        if any(word in summary_lower for word in ['urgent', 'immediate', 'critical', 'emergency']):
            urgency = "urgent"
        elif any(word in summary_lower for word in ['routine', 'regular', 'standard']):
            urgency = "routine"
        
        return {
            "complexity": complexity,
            "category": category,
            "urgency": urgency
        }
    
    def _analyze_multiple_perspectives(self,
                                     clean_summary: str,
                                     extracted_arguments: Dict[str, List[str]],
                                     risk_factors: List[str],
                                     opportunity_factors: List[str],
                                     governance_implications: List[str],
                                     economic_implications: List[str]) -> Dict[str, Any]:
        """Perform multi-delegate perspective analysis using unified multi_perspective module."""
        
        try:
            # Check if we have access to LLM for perspective analysis
            if not hasattr(self.reasoning_agent, 'reasoner') or not self.reasoning_agent.reasoner:
                logger.warning("No LLM available for perspective analysis")
                return self._create_empty_perspective_data()
            
            # Create LLM adapter for multi_perspective module
            llm = DelegateLLMAdapter(self.reasoning_agent.reasoner.llm)
            
            # Create a parser that uses pre-parsed input
            class PreParsedParser:
                def __init__(self, parsed_input: ParsedInput):
                    self._parsed_input = parsed_input
                
                def parse(self, data: Any) -> ParsedInput:
                    return self._parsed_input
            
            # Build ParsedInput from existing data
            parsed_input = ParsedInput(
                clean_summary=clean_summary,
                arguments=extracted_arguments,
                risk_factors=risk_factors + governance_implications,
                opportunity_factors=opportunity_factors,
                economic_implications=economic_implications,
            )
            
            # Initialize multi-perspective analyzer with predefined perspectives
            logger.info("Starting multi-perspective analysis...")
            analyzer = MultiPerspectiveAnalyzer(
                llm=llm,
                parser=PreParsedParser(parsed_input),
                perspectives=["conservative", "progressive", "balanced", "technical"],
            )
            
            # Run analysis
            result = analyzer.analyze(None)  # Data is in parser
            
            # Convert result to legacy format for backward compatibility
            perspective_analyses = []
            for analysis in result.analyses:
                perspective_analyses.append({
                    'perspective': analysis.perspective,
                    'analysis': analysis.analysis,
                    'focus_areas': analysis.focus_areas,
                    'key_concerns': analysis.key_concerns,
                    'key_benefits': analysis.key_benefits,
                    'recommendation_tendency': analysis.recommendation_tendency,
                    'confidence': analysis.confidence,
                })
            
            logger.info(f"Multi-perspective analysis complete: {len(perspective_analyses)} perspectives analyzed")
            
            return {
                "analyses": perspective_analyses,
                "synthesis": result.synthesis,
                "perspectives_analyzed": result.perspectives_analyzed,
                "consensus": result.consensus,
                "dominant_perspective": result.dominant_perspective,
            }
            
        except Exception as e:
            logger.error(f"Multi-perspective analysis failed: {str(e)}")
            return self._create_empty_perspective_data()
    
    def _create_empty_perspective_data(self) -> Dict[str, Any]:
        """Create empty perspective data structure"""
        return {
            "analyses": [],
            "synthesis": "Multi-perspective analysis not available",
            "perspectives_analyzed": [],
            "consensus": "unknown",
            "dominant_perspective": ""
        }
    
    def _analyze_perspective_consensus(self, perspective_analyses: List[Dict[str, Any]]) -> Dict[str, str]:
        """Analyze consensus and dominance among perspectives"""
        
        if not perspective_analyses:
            return {"consensus": "unknown", "dominant_perspective": ""}
        
        # Count recommendation tendencies
        tendencies = [analysis.get('recommendation_tendency', 'neutral') for analysis in perspective_analyses]
        tendency_counts = {}
        for tendency in tendencies:
            tendency_counts[tendency] = tendency_counts.get(tendency, 0) + 1
        
        # Determine consensus
        total_perspectives = len(perspective_analyses)
        max_count = max(tendency_counts.values()) if tendency_counts else 0
        
        if max_count == total_perspectives:
            consensus = "unanimous"
        elif max_count >= total_perspectives * 0.75:
            consensus = "majority"
        elif max_count >= total_perspectives * 0.5:
            consensus = "mixed"
        else:
            consensus = "split"
        
        # Find dominant perspective (highest confidence)
        dominant_perspective = ""
        max_confidence = 0
        for analysis in perspective_analyses:
            confidence = analysis.get('confidence', 0)
            if confidence > max_confidence:
                max_confidence = confidence
                dominant_perspective = analysis.get('perspective', '')
        
        return {
            "consensus": consensus,
            "dominant_perspective": dominant_perspective
        }

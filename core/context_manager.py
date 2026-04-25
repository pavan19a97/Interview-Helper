"""
Conversation Context Manager
Tracks Q&A history, analyzes question relationships, and provides context for LLM.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import re


class QuestionType(Enum):
    """Types of questions based on relationship to previous questions"""
    NEW_TOPIC = "new_topic"           # Independent new question
    REPHRASED = "rephrased"          # Same question asked differently
    FOLLOW_UP = "follow_up"          # Builds on previous answer
    CLARIFICATION = "clarification"  # Asks for more detail


@dataclass
class QAPair:
    """Represents a single question-answer pair"""
    question: str
    answer: str
    question_type: QuestionType = QuestionType.NEW_TOPIC
    related_to: Optional[int] = None  # Index of related Q&A pair
    timestamp: float = 0
    
    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "question_type": self.question_type.value,
            "related_to": self.related_to
        }


class ConversationContext:
    """Manages conversation history and context"""
    
    def __init__(self, max_history: int = 5):
        self.max_history = max_history
        self.history: List[QAPair] = []
        self.current_question: Optional[str] = None
    
    def add_question(self, question: str) -> None:
        """Record a new question from the interviewer"""
        self.current_question = question
    
    def add_answer(self, answer: str) -> None:
        """Record the AI's answer to the current question"""
        if self.current_question:
            # Analyze question type before adding
            qa_pair = QAPair(
                question=self.current_question,
                answer=answer,
                question_type=self._analyze_question_type()
            )
            self.history.append(qa_pair)
            
            # Trim history if needed
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
            
            self.current_question = None
    
    def _analyze_question_type(self) -> QuestionType:
        """Analyze the current question's relationship to previous ones"""
        if not self.history:
            return QuestionType.NEW_TOPIC
        
        current_q = self.current_question.lower() if self.current_question else ""
        last_qa = self.history[-1]
        last_q = last_qa.question.lower()
        
        # Check for follow-up patterns
        follow_up_patterns = [
            r'\b(how|what|why|can you|could you|tell me)\b.*\b(more|further|detail|explain)\b',
            r'\b(follow up|related to|building on|regarding)\b',
            r'\b(and|so|then)\b.*\b(about|regarding)\b',
        ]
        for pattern in follow_up_patterns:
            if re.search(pattern, current_q):
                return QuestionType.FOLLOW_UP
        
        # Check for rephrased questions (similar keywords, different wording)
        current_words = set(re.findall(r'\b\w{4,}\b', current_q))
        last_words = set(re.findall(r'\b\w{4,}\b', last_q))
        
        if current_words and last_words:
            overlap = len(current_words & last_words)
            total = len(current_words | last_words)
            similarity = overlap / total if total > 0 else 0
            
            # High similarity but not identical = rephrased
            if similarity > 0.4 and current_q != last_q:
                return QuestionType.REPHRASED
        
        # Check for clarification patterns
        clarify_patterns = [
            r'\b(sorry|clarify|what do you mean|explain what you mean)\b',
            r'\b(can you repeat|repeat that|go back)\b',
        ]
        for pattern in clarify_patterns:
            if re.search(pattern, current_q):
                return QuestionType.CLARIFICATION
        
        return QuestionType.NEW_TOPIC
    
    def get_context_for_llm(self) -> str:
        """Build context string to include with LLM prompts"""
        if not self.history:
            return ""
        
        context_parts = []
        context_parts.append("CONVERSATION HISTORY:")
        
        for i, qa in enumerate(self.history):
            type_label = {
                QuestionType.NEW_TOPIC: "[NEW]",
                QuestionType.REPHRASED: "[REPHRASED]",
                QuestionType.FOLLOW_UP: "[FOLLOW-UP]",
                QuestionType.CLARIFICATION: "[CLARIFY]"
            }.get(qa.question_type, "[NEW]")
            
            context_parts.append(f"\n--- Exchange {i+1} {type_label} ---")
            context_parts.append(f"Interviewer: {qa.question}")
            context_parts.append(f"AI: {qa.answer}")
        
        return "\n".join(context_parts)
    
    def get_recent_context(self, count: int = 3) -> str:
        """Get only the most recent N exchanges for context"""
        if not self.history:
            return ""
        
        recent = self.history[-count:]
        context_parts = []
        
        for qa in recent:
            context_parts.append(f"Q: {qa.question}")
            context_parts.append(f"A: {qa.answer}\n")
        
        return "\n".join(context_parts)
    
    def clear(self) -> None:
        """Clear all conversation history"""
        self.history.clear()
        self.current_question = None
    
    def get_summary(self) -> dict:
        """Get a summary of the conversation"""
        return {
            "total_exchanges": len(self.history),
            "question_types": {
                qt.value: sum(1 for qa in self.history if qa.question_type == qt)
                for qt in QuestionType
            },
            "recent_questions": [qa.question[-50:] + "..." if len(qa.question) > 50 else qa.question 
                                  for qa in self.history[-3:]]
        }


# Global context instance
_context = ConversationContext(max_history=5)


def get_context() -> ConversationContext:
    """Get the global conversation context"""
    return _context


def reset_context() -> None:
    """Reset the global conversation context"""
    _context.clear()
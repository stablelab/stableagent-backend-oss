"""
Pydantic schemas for Form Management in App Automation Agent.

Mirrors the TypeScript types from forse-growth-agent:
- packages/types/src/validation.ts
- packages/types/src/dynamic-form.ts
- backend/src/validation/forms.schemas.ts
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
import re

from pydantic import BaseModel, Field, field_validator


# ===========================
# Field Types and Enums
# ===========================

FieldType = Literal[
    "text",
    "textarea", 
    "number",
    "email",
    "url",
    "select",
    "multiselect",
    "checkbox",
    "radio",
    "date",
    "file",
    "array",
    "object",
]

ConditionalOperator = Literal[
    "equals",
    "notEquals",
    "contains",
    "greaterThan",
    "lessThan",
]

ConditionalAction = Literal[
    "show",
    "hide",
    "require",
    "disable",
]

SubmissionMethod = Literal["POST", "PUT", "PATCH"]


# ===========================
# Base Form Configuration Models
# ===========================

class SelectOption(BaseModel):
    """Option for select/multiselect/radio fields."""
    value: str
    label: str


class FieldValidationRules(BaseModel):
    """Validation rules for form fields."""
    required: Optional[bool] = None
    minLength: Optional[int] = None
    maxLength: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    pattern: Optional[str] = None
    email: Optional[bool] = None
    minItems: Optional[int] = None
    maxItems: Optional[int] = None
    custom: Optional[str] = None


class ConditionalRule(BaseModel):
    """Conditional display/behavior rules for fields."""
    field: str
    operator: ConditionalOperator
    value: Any
    action: ConditionalAction


class DynamicFormFieldProps(BaseModel):
    """Additional properties for form fields."""
    evaluationInstructions: Optional[str] = None
    aiEvaluation: Optional[bool] = True  # Default true - when false, field excluded from AI evaluation
    
    class Config:
        extra = "allow"  # Allow additional unknown properties


class DynamicFormField(BaseModel):
    """A single field in a form step."""
    id: str
    type: FieldType
    label: str
    placeholder: Optional[str] = None
    description: Optional[str] = None
    validation: Optional[FieldValidationRules] = None
    options: Optional[List[SelectOption]] = None
    props: Optional[DynamicFormFieldProps] = None
    conditional: Optional[List[ConditionalRule]] = None
    itemType: Optional[FieldType] = None
    itemSchema: Optional[Dict[str, Any]] = None
    defaultValue: Optional[Any] = None


class DynamicFormStep(BaseModel):
    """A step (section) in a form."""
    id: str
    title: str
    description: Optional[str] = None
    isOptional: Optional[bool] = False
    fields: List[DynamicFormField]


class SubmissionConfig(BaseModel):
    """Configuration for form submission."""
    endpoint: str = "/api/grants"
    method: SubmissionMethod = "POST"
    successMessage: str = "Your application has been submitted successfully!"
    errorMessage: str = "Failed to submit application"


class DynamicFormConfig(BaseModel):
    """Complete form configuration."""
    formId: str
    title: str
    description: Optional[str] = None
    steps: List[DynamicFormStep]
    submission: SubmissionConfig
    allow_custom_milestones: Optional[bool] = None


# ===========================
# Simplified Input Schemas (LLM-friendly)
# ===========================

class FormFieldInput(BaseModel):
    """Simplified field input for LLM-generated forms."""
    label: str = Field(..., description="Field label shown to user")
    type: FieldType = Field(..., description="Field type: text, textarea, number, email, url, select, multiselect, checkbox, radio, date, file")
    placeholder: Optional[str] = Field(None, description="Placeholder text shown in empty field")
    description: Optional[str] = Field(None, description="Help text shown below the field")
    required: bool = Field(False, description="Whether field is required")
    min_length: Optional[int] = Field(None, description="Minimum text length (for text/textarea)")
    max_length: Optional[int] = Field(None, description="Maximum text length (for text/textarea)")
    min_value: Optional[int] = Field(None, description="Minimum number value (for number fields)")
    max_value: Optional[int] = Field(None, description="Maximum number value (for number fields)")
    options: Optional[List[str]] = Field(None, description="Options for select/radio/multiselect fields (list of option labels)")


class FormStepInput(BaseModel):
    """Simplified step input for LLM-generated forms."""
    title: str = Field(..., description="Step title (e.g., 'Project Basics', 'Team Information')")
    description: Optional[str] = Field(None, description="Step description/instructions")
    fields: List[FormFieldInput] = Field(..., description="Fields in this step")


class CreateFormInput(BaseModel):
    """Input schema for CreateFormTool."""
    title: str = Field(..., description="Form title")
    description: Optional[str] = Field(None, description="Form description")
    program_id: Optional[int] = Field(None, description="Program ID to associate form with (use list_programs to find)")
    steps: List[FormStepInput] = Field(..., description="List of form steps with fields")


class UpdateFormInput(BaseModel):
    """Input schema for UpdateFormTool."""
    form_id: int = Field(..., description="ID of the form to update")
    title: Optional[str] = Field(None, description="New form title")
    description: Optional[str] = Field(None, description="New form description")
    program_id: Optional[int] = Field(None, description="New program ID to associate with")
    steps: Optional[List[FormStepInput]] = Field(None, description="Updated form steps (replaces all existing steps)")


# ===========================
# API Request/Response Schemas
# ===========================

class CreateFormRequest(BaseModel):
    """Request body for POST /api/forms."""
    config: DynamicFormConfig
    id_program: Optional[int] = None
    funding_amount_field_id: Optional[str] = None


class CreateFormResponse(BaseModel):
    """Response from POST /api/forms."""
    id: int
    formId: str


class FormListItem(BaseModel):
    """Single form in list response."""
    id: int
    formId: str
    title: str
    description: Optional[str] = None
    programId: Optional[int] = None
    fundingAmountFieldId: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    ownerId: Optional[int] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class FormListResponse(BaseModel):
    """Response from GET /api/forms."""
    forms: List[FormListItem]


class FormConfigResponse(BaseModel):
    """Response from GET /api/forms/config/{formId}."""
    formId: str
    title: str
    description: Optional[str] = None
    steps: List[DynamicFormStep]
    submission: SubmissionConfig
    id: Optional[int] = None
    form_id: Optional[int] = None
    allow_custom_milestones: Optional[bool] = None
    proposal_link_mode: Optional[str] = None
    wallet_address_collection_enabled: Optional[bool] = None
    
    class Config:
        extra = "allow"  # Allow extra fields for backward compatibility


class UpdateFormRequest(BaseModel):
    """Request body for PUT /api/forms/{formId}."""
    config: DynamicFormConfig
    id_program: Optional[int] = None
    funding_amount_field_id: Optional[str] = None
    proposal_link_mode: Optional[str] = None
    wallet_address_collection_enabled: Optional[bool] = None


class UpdateFormResponse(BaseModel):
    """Response from PUT /api/forms/{formId}."""
    id: int
    formId: str


# ===========================
# Program Schemas
# ===========================

class ProgramListItem(BaseModel):
    """Single program in list response."""
    id: int
    name: str
    start: Optional[int] = None
    end: Optional[int] = None
    total_budget: Optional[float] = None
    budget_currency: Optional[str] = None


class ProgramListResponse(BaseModel):
    """Response from GET /api/programs."""
    programs: List[ProgramListItem]


class GetProgramResponse(BaseModel):
    """Response from GET /api/programs/{id}."""
    id: int
    name: str
    start: Optional[int] = None  # Unix timestamp ms
    end: Optional[int] = None    # Unix timestamp ms
    total_budget: Optional[float] = None
    budget_currency: str = "USD"


class CreateProgramResponse(BaseModel):
    """Response from POST /api/programs."""
    id: int


class UpdateProgramResponse(BaseModel):
    """Response from PUT /api/programs/{id}."""
    id: int


# ===========================
# Program Input Schemas (LLM-friendly)
# ===========================

class GetProgramInput(BaseModel):
    """Input schema for GetProgramTool."""
    program_id: int = Field(..., description="ID of the program to retrieve")


class CreateProgramInput(BaseModel):
    """Input schema for CreateProgramTool."""
    name: str = Field(..., description="Program name (e.g., 'DeFi Builder Grants Q1 2025')")
    start: Optional[int] = Field(None, description="Start date as Unix timestamp in milliseconds. Use current time if not specified.")
    end: Optional[int] = Field(None, description="End date as Unix timestamp in milliseconds")
    total_budget: Optional[float] = Field(None, description="Total budget amount for the program")
    budget_currency: str = Field("USD", description="Budget currency (default: USD)")


class UpdateProgramInput(BaseModel):
    """Input schema for UpdateProgramTool."""
    program_id: int = Field(..., description="ID of the program to update")
    name: Optional[str] = Field(None, description="New program name")
    start: Optional[int] = Field(None, description="New start date as Unix timestamp in milliseconds")
    end: Optional[int] = Field(None, description="New end date as Unix timestamp in milliseconds")
    total_budget: Optional[float] = Field(None, description="New total budget amount")
    budget_currency: Optional[str] = Field(None, description="New budget currency")


class DeleteProgramInput(BaseModel):
    """Input schema for DeleteProgramTool."""
    program_id: int = Field(..., description="ID of the program to delete")


class CreateProgramWithFormInput(BaseModel):
    """Input schema for CreateProgramWithFormTool - creates both in one approval."""
    # Program fields
    program_name: str = Field(..., description="Name for the new program")
    program_start: Optional[int] = Field(None, description="Program start date as Unix timestamp in milliseconds")
    program_end: Optional[int] = Field(None, description="Program end date as Unix timestamp in milliseconds")
    total_budget: Optional[float] = Field(None, description="Total budget for the program")
    budget_currency: str = Field("USD", description="Budget currency (default: USD)")
    # Form fields
    form_title: str = Field(..., description="Title for the application form")
    form_description: Optional[str] = Field(None, description="Description for the application form")
    form_steps: List[FormStepInput] = Field(..., description="Form steps with fields")


# ===========================
# Utility Functions
# ===========================

def generate_field_id(label: str, existing_ids: set) -> str:
    """
    Generate a unique field ID from a label.
    
    Converts to kebab-case and ensures uniqueness.
    E.g., "Team Experience" -> "team-experience"
    
    Args:
        label: The field label
        existing_ids: Set of already-used IDs
        
    Returns:
        Unique field ID string
    """
    # Convert to lowercase and replace spaces/special chars with hyphens
    base_id = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')
    
    # Ensure it doesn't start with a number
    if base_id and base_id[0].isdigit():
        base_id = f"field-{base_id}"
    
    # Handle empty result
    if not base_id:
        base_id = "field"
    
    # Ensure uniqueness
    final_id = base_id
    counter = 1
    while final_id in existing_ids:
        final_id = f"{base_id}-{counter}"
        counter += 1
    
    return final_id


def generate_step_id(title: str, existing_ids: set) -> str:
    """
    Generate a unique step ID from a title.
    
    Args:
        title: The step title
        existing_ids: Set of already-used IDs
        
    Returns:
        Unique step ID string
    """
    # Convert to lowercase and replace spaces/special chars with hyphens
    base_id = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    
    # Handle empty result
    if not base_id:
        base_id = "step"
    
    # Ensure uniqueness
    final_id = base_id
    counter = 1
    while final_id in existing_ids:
        final_id = f"{base_id}-{counter}"
        counter += 1
    
    return final_id


def convert_simplified_to_full_config(
    title: str,
    steps: List[FormStepInput],
    description: Optional[str] = None,
) -> DynamicFormConfig:
    """
    Convert simplified LLM-friendly input to full DynamicFormConfig.
    
    Args:
        title: Form title
        steps: List of simplified step inputs
        description: Optional form description
        
    Returns:
        Complete DynamicFormConfig ready for API
    """
    # Generate form ID from title
    form_id = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    if not form_id:
        form_id = "form"
    
    # Track used IDs for uniqueness
    step_ids: set = set()
    
    converted_steps: List[DynamicFormStep] = []
    
    for step_input in steps:
        # Generate step ID
        step_id = generate_step_id(step_input.title, step_ids)
        step_ids.add(step_id)
        
        # Track field IDs within this form (global uniqueness)
        field_ids: set = set()
        converted_fields: List[DynamicFormField] = []
        
        for field_input in step_input.fields:
            # Generate field ID
            field_id = generate_field_id(field_input.label, field_ids)
            field_ids.add(field_id)
            
            # Build validation rules
            validation = FieldValidationRules(
                required=field_input.required if field_input.required else None,
                minLength=field_input.min_length,
                maxLength=field_input.max_length,
                min=field_input.min_value,
                max=field_input.max_value,
            )
            
            # Only include validation if there are actual rules
            has_validation = any([
                field_input.required,
                field_input.min_length,
                field_input.max_length,
                field_input.min_value,
                field_input.max_value,
            ])
            
            # Convert options if provided
            options = None
            if field_input.options:
                options = [
                    SelectOption(value=opt.lower().replace(' ', '-'), label=opt)
                    for opt in field_input.options
                ]
            
            # Build the field
            field = DynamicFormField(
                id=field_id,
                type=field_input.type,
                label=field_input.label,
                placeholder=field_input.placeholder,
                description=field_input.description,
                validation=validation if has_validation else None,
                options=options,
            )
            converted_fields.append(field)
        
        # Build the step
        step = DynamicFormStep(
            id=step_id,
            title=step_input.title,
            description=step_input.description,
            isOptional=False,
            fields=converted_fields,
        )
        converted_steps.append(step)
    
    # Build the complete config
    config = DynamicFormConfig(
        formId=form_id,
        title=title,
        description=description,
        steps=converted_steps,
        submission=SubmissionConfig(),  # Use defaults
    )
    
    return config


def format_form_config_for_display(config: Dict[str, Any]) -> str:
    """
    Format a form configuration as human-readable text.
    
    Args:
        config: Form configuration dict
        
    Returns:
        Formatted string representation
    """
    lines = []
    
    title = config.get('title', 'Untitled Form')
    form_id = config.get('formId', 'unknown')
    description = config.get('description', '')
    
    lines.append(f"Form: {title} (ID: {form_id})")
    if description:
        lines.append(f"Description: {description}")
    lines.append("")
    
    steps = config.get('steps', [])
    for i, step in enumerate(steps, 1):
        step_title = step.get('title', f'Step {i}')
        step_desc = step.get('description', '')
        is_optional = step.get('isOptional', False)
        
        optional_marker = " (Optional)" if is_optional else ""
        lines.append(f"Step {i}: {step_title}{optional_marker}")
        if step_desc:
            lines.append(f"  {step_desc}")
        
        fields = step.get('fields', [])
        for field in fields:
            field_id = field.get('id', 'unknown')
            field_type = field.get('type', 'text')
            field_label = field.get('label', 'Unnamed Field')
            validation = field.get('validation', {}) or {}
            
            required = "required" if validation.get('required') else "optional"
            
            field_line = f"  - {field_label} [{field_type}, {required}]"
            
            # Add validation details
            validation_parts = []
            if validation.get('minLength'):
                validation_parts.append(f"min {validation['minLength']} chars")
            if validation.get('maxLength'):
                validation_parts.append(f"max {validation['maxLength']} chars")
            if validation.get('min') is not None:
                validation_parts.append(f"min value {validation['min']}")
            if validation.get('max') is not None:
                validation_parts.append(f"max value {validation['max']}")
            
            if validation_parts:
                field_line += f" ({', '.join(validation_parts)})"
            
            lines.append(field_line)
            
            # Show options for select fields
            options = field.get('options', [])
            if options:
                option_labels = [opt.get('label', opt.get('value', '')) for opt in options]
                lines.append(f"    Options: {', '.join(option_labels)}")
        
        lines.append("")
    
    return "\n".join(lines)


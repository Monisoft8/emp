# msd/utils/excel.py
"""
Excel utilities for column normalization and data extraction
"""

import pandas as pd
from typing import Dict, Any, Optional


# Arabic to English column mapping
ARABIC_COLUMN_MAP = {
    # Arabic column names to English equivalents
    'الاسم': 'name',
    'الرقم الوطني': 'national_id',
    'الرقم الآلي': 'serial_number',
    'القسم': 'department',
    'الدرجة الوظيفية': 'job_grade',
    'الدرجة': 'job_grade',
    'تاريخ التعيين': 'hiring_date',
    'تاريخ الدرجة': 'grade_date',
    'العلاوة': 'bonus',
    'رصيد الإجازات': 'vacation_balance',
    'أيام العمل': 'work_days',
    
    # English column names (already mapped)
    'name': 'name',
    'national_id': 'national_id',
    'serial_number': 'serial_number',
    'department': 'department',
    'job_grade': 'job_grade',
    'hiring_date': 'hiring_date',
    'grade_date': 'grade_date',
    'bonus': 'bonus',
    'vacation_balance': 'vacation_balance',
    'work_days': 'work_days'
}


def normalize_column_names(df: pd.DataFrame) -> Dict[str, str]:
    """
    Normalize column names from Arabic/English to standard English names
    Returns a mapping of actual column names to normalized names
    """
    actual_columns = {}
    df_columns = [str(col).strip() for col in df.columns]
    
    for actual_col in df_columns:
        # Try direct match first
        if actual_col in ARABIC_COLUMN_MAP:
            normalized = ARABIC_COLUMN_MAP[actual_col]
            actual_columns[normalized] = actual_col
            continue
        
        # Try case-insensitive match
        for arabic_col, eng_col in ARABIC_COLUMN_MAP.items():
            if actual_col.lower() == arabic_col.lower() or actual_col.lower() == eng_col.lower():
                actual_columns[eng_col] = actual_col
                break
    
    return actual_columns


def safe_extract_value(row: pd.Series, column: str, default: Any = '') -> Any:
    """
    Safely extract value from pandas row, handling NaN and missing columns
    """
    if column not in row:
        return default
    
    value = row[column]
    if pd.isna(value):
        return default
    
    return value


def normalize_date(date_value: Any) -> str:
    """
    Normalize date value to YYYY-MM-DD format
    """
    if not date_value or pd.isna(date_value):
        return ''
    
    date_str = str(date_value).strip()
    if not date_str:
        return ''
    
    # Handle pandas timestamp
    if hasattr(date_value, 'strftime'):
        return date_value.strftime('%Y-%m-%d')
    
    # Handle various date formats
    try:
        # Split on space to remove time component
        date_part = date_str.split(' ')[0]
        
        # Try to parse and reformat
        if '/' in date_part:
            # Handle MM/DD/YYYY or DD/MM/YYYY
            parts = date_part.split('/')
            if len(parts) == 3:
                if len(parts[2]) == 4:  # YYYY
                    return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
        elif '-' in date_part:
            # Already in YYYY-MM-DD or similar format
            parts = date_part.split('-')
            if len(parts) == 3:
                if len(parts[0]) == 4:  # YYYY-MM-DD
                    return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                elif len(parts[2]) == 4:  # DD-MM-YYYY
                    return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        
        return date_str
    except:
        return date_str


def validate_national_id(national_id: Any) -> tuple[bool, str]:
    """
    Validate national ID format
    Returns (is_valid, normalized_value)
    """
    if not national_id or pd.isna(national_id):
        return False, ''
    
    national_id_str = str(national_id).strip()
    
    # Remove any non-digit characters
    digits_only = ''.join(filter(str.isdigit, national_id_str))
    
    if len(digits_only) != 12:
        return False, digits_only
    
    return True, digits_only


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to integer
    """
    if not value or pd.isna(value):
        return default
    
    try:
        # Handle string values
        if isinstance(value, str):
            # Remove any non-digit characters except minus
            cleaned = ''.join(filter(lambda x: x.isdigit() or x == '-', value.strip()))
            if not cleaned or cleaned == '-':
                return default
            return int(cleaned)
        
        # Handle numeric values
        return int(float(value))
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float
    """
    if not value or pd.isna(value):
        return default
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
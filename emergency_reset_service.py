"""Emergency vacation balance reset service."""
import logging
from datetime import date
from msd.database.connection import get_conn

logger = logging.getLogger(__name__)


def run_emergency_reset():
    """Reset emergency vacation balance on January 1st (idempotent)."""
    current_date = date.today()
    year = current_date.year
    
    # Only run on January 1st
    if current_date.month != 1 or current_date.day != 1:
        return
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Check if reset already ran for this year
        cur.execute("SELECT 1 FROM emergency_reset_log WHERE year = ?", (year,))
        if cur.fetchone():
            logger.info(f"Emergency reset already processed for year {year}")
            return
        
        # Reset emergency vacation balance for all active employees
        cur.execute("""
            UPDATE employees 
            SET emergency_vacation_balance = 12, updated_at = CURRENT_TIMESTAMP
            WHERE status = 'active'
        """)
        
        reset_count = cur.rowcount
        
        # Log the reset
        cur.execute("INSERT INTO emergency_reset_log (year) VALUES (?)", (year,))
        
        conn.commit()
        logger.info(f"Emergency vacation reset completed for year {year}. Reset {reset_count} employees.")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error running emergency reset: {e}")
        raise
    finally:
        conn.close()
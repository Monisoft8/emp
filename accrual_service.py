"""Monthly vacation accrual service."""
import logging
from datetime import datetime, date
from msd.database.connection import get_conn

logger = logging.getLogger(__name__)


def run_monthly_accrual():
    """Run monthly vacation accrual for all active employees (idempotent)."""
    current_date = date.today()
    year = current_date.year
    month = current_date.month
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Check if accrual already ran for this month
        cur.execute("SELECT 1 FROM accrual_log WHERE year = ? AND month = ?", (year, month))
        if cur.fetchone():
            logger.info(f"Monthly accrual already processed for {year}-{month:02d}")
            return
        
        # Get all active employees with hiring dates
        cur.execute("""
            SELECT id, name, hiring_date, vacation_balance
            FROM employees 
            WHERE status = 'active' AND hiring_date IS NOT NULL AND hiring_date != ''
        """)
        employees = cur.fetchall()
        
        accrued_count = 0
        
        for employee in employees:
            employee_id = employee["id"]
            name = employee["name"]
            hiring_date_str = employee["hiring_date"]
            current_balance = employee["vacation_balance"] or 0
            
            try:
                # Parse hiring date
                hiring_date = datetime.strptime(hiring_date_str, "%Y-%m-%d").date()
                
                # Calculate years of service
                years_of_service = (current_date - hiring_date).days / 365.25
                
                # Determine annual vacation quota based on years of service
                if years_of_service < 25:
                    annual_quota = 30
                else:
                    annual_quota = 45
                
                # Monthly accrual = annual quota / 12
                monthly_accrual = annual_quota / 12.0
                
                # Update vacation balance
                new_balance = current_balance + monthly_accrual
                
                cur.execute("""
                    UPDATE employees 
                    SET vacation_balance = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_balance, employee_id))
                
                accrued_count += 1
                logger.debug(f"Accrued {monthly_accrual:.2f} days for {name} (ID: {employee_id})")
                
            except ValueError as e:
                logger.warning(f"Invalid hiring date for employee {name} (ID: {employee_id}): {e}")
            except Exception as e:
                logger.error(f"Error processing accrual for employee {name} (ID: {employee_id}): {e}")
        
        # Log the accrual run
        cur.execute("INSERT INTO accrual_log (year, month) VALUES (?, ?)", (year, month))
        
        conn.commit()
        logger.info(f"Monthly accrual completed for {year}-{month:02d}. Processed {accrued_count} employees.")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error running monthly accrual: {e}")
        raise
    finally:
        conn.close()
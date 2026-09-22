"""
SATQUERY AI — Configuration checker
Run before deploying to verify your .env is complete.
Usage: python scripts/check_config.py [path/to/.env]
"""
import sys, os

env_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), '..', 'backend', '.env'
)

# Load .env file if it exists
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())

# Run the startup validator
backend = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, backend)

from services.startup_validator import validate_startup
flask_env = os.environ.get('FLASK_ENV', 'development')
result = validate_startup(flask_env)

print(f"\nConfiguration check: {'PASSED' if result['ok'] else 'FAILED'}")
if not result['ok']:
    print(f"Missing required variables: {result['missing_required']}")
    sys.exit(1)

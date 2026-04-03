import pkg_resources
import logging
from pathlib import Path

# Setup logging for a clean output
logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_dependencies(requirements_file="backend/requirements.txt"):
    requirements_path = Path(requirements_file)
    
    if not requirements_path.exists():
        logging.error(f"Error: {requirements_file} not found!")
        return

    logging.info(f"--- Checking Dependencies from {requirements_file} ---\n")
    
    with open(requirements_path, "r") as f:
        # Filter out comments and empty lines
        requirements = [
            line.strip() for line in f 
            if line.strip() and not line.startswith("#")
        ]

    missing_packages = []
    outdated_packages = []
    installed_count = 0

    for requirement in requirements:
        try:
            # This handles version specs like ==, >=, etc.
            pkg_resources.require(requirement)
            logging.info(f"{requirement:<30} [INSTALLED]")
            installed_count += 1
        except pkg_resources.DistributionNotFound:
            logging.error(f"{requirement:<30} [MISSING]")
            missing_packages.append(requirement)
        except pkg_resources.VersionConflict as e:
            logging.warning(f"{requirement:<30} [VERSION CONFLICT - Found {e.req}]")
            outdated_packages.append(requirement)

    print("\n" + "="*50)
    print(f"SUMMARY:")
    print(f"Total Requirements: {len(requirements)}")
    print(f"Successfully Verified: {installed_count}")
    
    if missing_packages or outdated_packages:
        print(f"\nISSUES FOUND:")
        if missing_packages:
            print(f"  - Missing: {len(missing_packages)}")
        if outdated_packages:
            print(f"  - Conflicts: {len(outdated_packages)}")
        print("\nACTION REQUIRED: Run the following command:")
        print(f"pip install -r {requirements_file}")
    else:
        print("\n All systems go! Your environment matches requirements.txt.")
    print("="*50 + "\n")

if __name__ == "__main__":
    # Adjust path if your requirements.txt is in a different folder
    check_dependencies("backend/requirements.txt")
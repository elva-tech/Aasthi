#!/usr/bin/env python3
import subprocess
import sys
import os
import re
from dotenv import load_dotenv

def run_step(command, cwd=None, capture_output=False):
    print(f"\n{'='*60}")
    print(f"🚀 Running Step: {' '.join(command)} (in {cwd or '.'})")
    print(f"{'='*60}")
    
    try:
        if capture_output:
            result = subprocess.run(
                command, 
                cwd=cwd, 
                text=True, 
                capture_output=True, 
                check=True
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.stdout
        else:
            subprocess.run(
                command, 
                cwd=cwd, 
                check=True
            )
            return None
    except subprocess.CalledProcessError as e:
        print(f"❌ Error occurred while running: {' '.join(command)}")
        if capture_output:
            print(f"Stdout:\n{e.stdout}")
            print(f"Stderr:\n{e.stderr}")
        sys.exit(e.returncode)

def main():
    base_dir = "/home/ravella/landed"
    load_dotenv(os.path.join(base_dir, "riskwrapper", ".env"))
    load_dotenv(os.path.join(base_dir, "reportgeneration", ".env"))
    
    # Step 1: Run EC fetcher and checks
    # Assuming riskwrapper/ec_wrapper.py is the EC fetcher as per the plan
    run_step(
        ["python3", "ec_wrapper.py"], 
        cwd=os.path.join(base_dir, "riskwrapper")
    )
    
    # Step 2: Run wrappercode/main.py
    run_step(
        ["python3", "main.py"], 
        cwd=os.path.join(base_dir, "wrappercode")
    )
    
    # Step 3: Run riskwrapper/main.py and capture output
    stdout = run_step(
        ["python3", "main.py"], 
        cwd=os.path.join(base_dir, "riskwrapper"),
        capture_output=True
    )
    
    # Step 4: Capture the JSON output path
    json_path = None
    # Look for the string: "🧾 JSON report saved : path/to/report.json"
    match = re.search(r"🧾 JSON report saved\s*:\s*(.*\.json)", stdout)
    if match:
        json_path = match.group(1).strip()
        # Since main.py runs in riskwrapper, the path might be relative to that directory.
        if not os.path.isabs(json_path):
            json_path = os.path.join(base_dir, "riskwrapper", json_path)
        print(f"\n✅ Captured JSON result path: {json_path}")
    else:
        print("\n❌ Failed to capture JSON output path from riskwrapper/main.py. Ensure the output format hasn't changed.")
        sys.exit(1)
        
    if not os.path.exists(json_path):
        print(f"\n❌ JSON report file does not exist at {json_path}")
        sys.exit(1)

    # Step 5: Run report_generator/report_generator.py using the JSON path
    # Actually the script is reportgeneration/generate_pdf_report.py
    report_output = os.path.join(base_dir, "reportgeneration", "output", "final_risk_report.pdf")
    os.makedirs(os.path.dirname(report_output), exist_ok=True)
    
    run_step(
        ["python3", "generate_pdf_report.py", "--input", json_path, "--out", report_output],
        cwd=os.path.join(base_dir, "reportgeneration")
    )
    
    print(f"\n🎉 Pipeline completed successfully! Final PDF generated at: {report_output}\n")

if __name__ == "__main__":
    main()

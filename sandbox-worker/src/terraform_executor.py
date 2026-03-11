import os
import subprocess
from logger import stream_log

def run_terraform(session_id: str, tf_code: str, is_final_retry: bool = False) -> tuple[str, str]:
    """
    Writes tf_code to disk, runs init -> validate -> plan -> apply.
    Returns (status: 'passed' or 'failed', feedback: 'error log or success msg')
    """
    work_dir = f"/tmp/{session_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    main_tf_path = os.path.join(work_dir, "main.tf")
    with open(main_tf_path, "w") as f:
        f.write(tf_code)
    stream_log(session_id, "[TF Executor] main.tf written to sandbox.")
    
    def exec_cmd(cmd: list, stage_name: str):
        if cmd[0] == "terraform" and "-input=false" not in cmd and cmd[1] not in ["validate", "destroy", "init"]:
            cmd.insert(2, "-input=false")
            
        stream_log(session_id, f"[STAGE: {stage_name}] $ {' '.join(cmd)}")
        
        env = os.environ.copy()
        project_id = env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCP_PROJECT") or env.get("GOOGLE_PROJECT")
        
        if not project_id:
            try:
                import google.auth
                _, project_id = google.auth.default()
            except Exception as e:
                stream_log(session_id, f"[Warning] Could not dynamically discover GCP project ID: {e}")
                
        if project_id:
            env["TF_VAR_project_id"] = project_id
            env["TF_VAR_project"] = project_id
            env["GOOGLE_PROJECT"] = project_id
            env["GOOGLE_CLOUD_PROJECT"] = project_id
        
        process = subprocess.Popen(
            cmd, cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        
        output_buffer = []
        for line in iter(process.stdout.readline, ''):
            clean_line = line.strip()
            if clean_line:
                stream_log(session_id, f"[STAGE: {stage_name}] {clean_line}")
            output_buffer.append(f"[STAGE: {stage_name}] {line}")
            
        process.stdout.close()
        return_code = process.wait()
        full_output = "".join(output_buffer)
        
        if return_code != 0:
            return False, full_output
        return True, full_output

    success, out = exec_cmd(["terraform", "init"], "INIT")
    if not success: return "failed", out
    
    success, out = exec_cmd(["terraform", "validate"], "VALIDATE")
    if not success: return "failed", out
    
    success, out = exec_cmd(["terraform", "plan", "-out=tfplan"], "PLAN")
    if not success: return "failed", out
    
    stream_log(session_id, "Terraform plan generated and validated successfully.")
    
    return "passed", "Successfully executed plan validation."

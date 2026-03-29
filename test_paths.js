import { runPythonWrappers } from './backend/python-runner.js';

async function test() {
    console.log("Starting test run of Python wrappers...");
    try {
        const result = await runPythonWrappers({
            ownerName: "TEST USER",
            projectName: "TEST PROJECT",
            sessionId: "test_session_" + Date.now()
        });
        console.log("Test execution finished.");
        console.log("Result:", JSON.stringify(result, null, 2));
    } catch (err) {
        console.error("Test failed:", err);
    }
}

test();

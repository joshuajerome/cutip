// .jenkins/docs.Jenkinsfile
// Triggered on push to staging (after feat/bug merge) or push to docs/**.
// Full AI-driven docs verification and deployment pipeline.
// Requires ANTHROPIC_API_KEY credential configured in Jenkins.
// Agent must have git configured with push access to the repo.

pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        PYTHONUTF8 = '1'
        // Bind the Jenkins credential named 'anthropic-api-key' to the env var
        ANTHROPIC_API_KEY = credentials('anthropic-api-key')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                // Full history required for mkdocs gh-deploy and git diff
                sh 'git fetch --unshallow 2>/dev/null || true'
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    uv venv .venv
                    uv pip install -e ".[docs]"
                    uv pip install anthropic
                '''
            }
        }

        stage('Analyze Code Changes') {
            steps {
                sh '''
                    git diff HEAD~1 --name-only -- "*.py" > /tmp/changed_files.txt
                    echo "Changed Python files:"
                    cat /tmp/changed_files.txt
                    uv run python .jenkins/scripts/analyze-doc-coverage.py
                '''
            }
        }

        stage('Scan Documentation for Outdated Content') {
            steps {
                sh 'uv run python .jenkins/scripts/scan-outdated-docs.py'
            }
        }

        stage('Scan for Vulnerabilities in Documentation') {
            steps {
                sh 'uv run python .jenkins/scripts/scan-doc-vulnerabilities.py'
            }
        }

        stage('Update README.md if Needed') {
            steps {
                sh 'uv run python .jenkins/scripts/update-readme.py'
            }
        }

        stage('Update GitHub Pages') {
            steps {
                sh 'uv run mkdocs gh-deploy --force'
            }
        }

        stage('Build with MkDocs & Verify') {
            steps {
                sh 'uv run mkdocs build --strict'
                sh '''
                    uv run python -m http.server 8000 --directory site &
                    SERVER_PID=$!
                    sleep 2
                    curl -f http://localhost:8000/ > /dev/null
                    curl -f http://localhost:8000/getting-started/installation/ > /dev/null
                    kill $SERVER_PID 2>/dev/null || true
                '''
            }
            post {
                always {
                    sh 'pkill -f "http.server 8000" 2>/dev/null || true'
                }
            }
        }
    }

    post {
        always {
            sh 'rm -rf .venv site/ /tmp/changed_files.txt 2>/dev/null || true'
        }
        failure {
            echo "Docs pipeline failed — check console output above for details."
        }
    }
}

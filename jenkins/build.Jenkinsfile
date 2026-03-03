// build.Jenkinsfile
// Triggered on push to feat/** or bug/** branches (or PR targeting staging).
// Mirrors GHA pr-checks.yml + wheel-build.yml.

pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    triggers {
        // Trigger on push to feat/** or bug/** via SCM webhook
        // Configure branch filter in Jenkins SCM plugin or Multibranch Pipeline
        pollSCM('')
    }

    environment {
        PYTHONUTF8 = '1'
        CUTIP_BACKEND_NAME = 'podman'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh 'uv sync'
            }
        }

        stage('Unit Tests') {
            steps {
                sh 'uv run pytest tests/ -v --ignore=tests/e2e --tb=short'
            }
            post {
                always {
                    // Archive JUnit XML if pytest-junit is configured
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                }
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    uv build --wheel
                    uv venv .wheel-test
                    uv pip install --python .wheel-test/bin/python dist/cutip-*.whl
                    .wheel-test/bin/python -c "import cutip; print('cutip import OK')"
                    .wheel-test/bin/cutip --help
                '''
            }
        }

        stage('E2E (Ubuntu / Podman)') {
            steps {
                sh '''
                    uv venv .venv
                    uv pip install -e .
                    uv run cutip validate --path tests/e2e/hello-world
                    uv run cutip run hello --path tests/e2e/hello-world --local
                '''
            }
        }

        stage('Build Wheel') {
            steps {
                sh 'uv build --wheel'
                sh 'ls -lh dist/'
            }
            post {
                success {
                    archiveArtifacts artifacts: 'dist/*.whl', fingerprint: true
                }
            }
        }
    }

    post {
        always {
            // Clean up ephemeral venvs
            sh 'rm -rf .wheel-test .venv dist/ 2>/dev/null || true'
        }
        failure {
            echo "Build failed — check console output above for details."
        }
    }
}

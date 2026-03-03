// .jenkins/docs.Jenkinsfile
// Triggered on push to staging (after feat/bug merge) or push to docs/**.
// Full AI-driven docs verification and deployment pipeline.
//
// Jenkins credentials required (ID must match exactly):
//   ANTHROPIC_API_KEY  - Anthropic API key (mirror of the GitHub repository secret)
//   GITHUB_TOKEN       - GitHub PAT with repo scope (for posting PR comments)
//
// Agent must have git configured with push access to the repo.

pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        PYTHONUTF8        = '1'
        ANTHROPIC_API_KEY = credentials('ANTHROPIC_API_KEY')
        GH_TOKEN          = credentials('GITHUB_TOKEN')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                // Full history required for mkdocs gh-deploy and git diff
                sh 'git fetch --unshallow 2>/dev/null || true'
                // Reports directory — written by AI scripts, archived as artifacts
                sh 'mkdir -p claude-reports'
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

        stage('Claude AI Summary') {
            steps {
                sh '''
                    SUMMARY=claude-reports/summary.md
                    BRANCH=$(git rev-parse --abbrev-ref HEAD)
                    RUN_DATE=$(date -u '+%Y-%m-%d %H:%M UTC')

                    # Compile all per-script reports into one summary
                    {
                        echo "## Claude Documentation Summary"
                        echo ""
                        echo "Branch: \`${BRANCH}\` | Run: ${RUN_DATE}"
                        echo ""
                        for report in \
                            claude-reports/analyze-doc-coverage.md \
                            claude-reports/scan-outdated-docs.md \
                            claude-reports/scan-doc-vulnerabilities.md \
                            claude-reports/update-readme.md; do
                            if [ -f "$report" ]; then
                                echo "---"
                                echo "### $(basename $report .md)"
                                echo ""
                                cat "$report"
                                echo ""
                            fi
                        done
                    } > "$SUMMARY"

                    echo "=== Claude AI Summary ==="
                    cat "$SUMMARY"

                    # Post as a PR comment if an open PR exists for this branch
                    PR_NUMBER=$(gh pr list --head "$BRANCH" --state open --json number \
                        --jq '.[0].number' 2>/dev/null || echo "")
                    if [ -n "$PR_NUMBER" ] && [ "$PR_NUMBER" != "null" ]; then
                        gh pr comment "$PR_NUMBER" --body "$(cat $SUMMARY)"
                        echo "Posted Claude summary to PR #${PR_NUMBER}"
                    else
                        echo "No open PR for branch '${BRANCH}' — summary not posted as comment"
                    fi
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'claude-reports/**', allowEmptyArchive: true
                }
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
            sh 'rm -rf .venv site/ claude-reports/ /tmp/changed_files.txt 2>/dev/null || true'
        }
        failure {
            echo "Docs pipeline failed — check console output above for details."
        }
    }
}

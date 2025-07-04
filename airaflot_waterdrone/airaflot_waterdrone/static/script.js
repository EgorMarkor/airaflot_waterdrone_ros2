let showAllLogs = false;
let showAllMeas = false;

function toggleParameters() {
    const modal = document.getElementById('parameters-modal');
    modal.style.display = modal.style.display === 'none' ? 'flex' : 'none';
}

function closeParametersModal() {
    const modal = document.getElementById('parameters-modal');
    modal.style.display = 'none';
}

function changeScenario(scenarioName) {
    fetch('/select_scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `scenario=${encodeURIComponent(scenarioName)}`
    })
    .then(() => location.reload())
    .catch(err => alert("Failed to change scenario: " + err.message));
}

function getStateClass(state) {
    if (state === "active") return "state-active";
    if (state === "dead") return "state-dead";
    if (state === "unconfigured") return "state-unconfigured";
    return "";
}

function loadParameters() {
    fetch('/project_state')
        .then(response => response.json())
        .then(data => {
            let html = "";
            let foundDepthParameter = false;
            
            for (const [node, params] of Object.entries(data.parameters)) {
                html += `<div class="node-section"><h3>${node}</h3><ul>`;
                params.forEach(param => {
                    // Check for default_depth parameter in water_sampler_scenario node
                    if (param.name === 'default_depth') {
                        foundDepthParameter = true;
                        currentDepthParameter = {
                            node: node,
                            name: param.name,
                            type: param.type,
                            value: param.value,
                            editable: param.editable
                        };
                        // Update the inline parameter display
                        updateInlineDepthParameter();
                    }
                    
                    const inputId = `${node}_${param.name}`;
                    html += `<li>${param.name}: `;
                    if (param.editable) {
                        if (param.type === 4) {
                            html += `<input type="text" id="${inputId}" value="${param.value}">`;
                        } else if (param.type === 1) {
                            html += `<input type="checkbox" id="${inputId}" ${param.value ? "checked" : ""}>`;
                        } else if (param.type === 2) {
                            html += `<input type="number" id="${inputId}" value="${param.value}">`;
                        }
                    } else {
                        html += `<span>${param.value}</span>`;
                    }
                    html += `</li>`;
                });
                html += "</ul></div>";
            }
            document.getElementById("parameters").innerHTML = html;
            
            // Show/hide inline depth parameter
            const inlineParam = document.getElementById('inline-depth-parameter');
            if (foundDepthParameter) {
                inlineParam.style.display = 'flex';
            } else {
                inlineParam.style.display = 'none';
                currentDepthParameter = null;
            }
        });
}

function updateInlineDepthParameter() {
    if (currentDepthParameter && currentDepthParameter.editable) {
        const depthInput = document.getElementById('depth-input');
        if (depthInput) {
            depthInput.value = currentDepthParameter.value;
        }
    }
}

function saveInlineDepthParameter() {
    if (!currentDepthParameter) return;
    
    const depthInput = document.getElementById('depth-input');
    const newValue = parseFloat(depthInput.value);
    
    if (isNaN(newValue)) {
        alert('Please enter a valid number for depth');
        return;
    }
    
    const updateData = [{
        node: currentDepthParameter.node,
        name: currentDepthParameter.name,
        type: currentDepthParameter.type,
        value: newValue
    }];
    
    fetch('/set_parameters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateData)
    }).then(response => response.text())
      .then(msg => {
        alert(msg);
        currentDepthParameter.value = newValue;
        loadParameters(); // Reload to sync both displays
      })
      .catch(err => {
        alert('Failed to save parameter: ' + err.message);
      });
}

function loadStatusAndNodes() {
    fetch('/project_state')
        .then(response => response.json())
        .then(data => {
            const stateElem = document.getElementById('scenario-state');
            stateElem.textContent = data.current_scenario.state;
            stateElem.className = getStateClass(data.state);

            const currentScenarioElem = document.getElementById('current-scenario');
            currentScenarioElem.textContent = data.current_scenario.name;

            const scenarioSelect = document.getElementById('scenario');
            const warningElem = document.getElementById('scenario-warning');
            const allUnconfigured = data.nodes.every(n => n.state === 'unconfigured');
            scenarioSelect.disabled = !allUnconfigured;
            warningElem.style.display = allUnconfigured ? 'none' : 'block';

            let list = '<ul>';
            data.nodes.forEach(n => {
                let action = n.state === "active" ? "deactivate" : "activate";
                let stateClass = getStateClass(n.state);
                list += `<li>${n.full_name}: <span class="${stateClass}">${n.state}</span> 
                            <button onclick="fetch('/node_action?name=${n.full_name}&action=${action}').then(response => response.text()).then(alert)">
                                ${action.charAt(0).toUpperCase() + action.slice(1)}
                            </button>
                         </li>`;
            });
            list += '</ul>';
            document.getElementById('nodes').innerHTML = list;

            const runBtn = document.getElementById('run-service-btn');
            if (runBtn) {
                const allActive = data.nodes.every(n => n.state === 'active');
                runBtn.disabled = !allActive;
            }
        });
}

function saveParameters() {
    fetch('/project_state')
        .then(response => response.json())
        .then(data => {
            let updated = [];
            for (const [node, params] of Object.entries(data.parameters)) {
                params.forEach(param => {
                    if (param.editable) {
                        const inputId = `${node}_${param.name}`;
                        let value;
                        if (param.type === 4) {
                            value = document.getElementById(inputId).value;
                        } else if (param.type === 1) {
                            value = document.getElementById(inputId).checked;
                        } else if (param.type === 2) {
                            value = parseFloat(document.getElementById(inputId).value);
                        }
                        updated.push({ node, name: param.name, type: param.type, value });
                    }
                });
            }

            fetch('/set_parameters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updated)
            }).then(response => response.text())
              .then(msg => {
                alert(msg);
                loadParameters();  // Reload parameters
                closeParametersModal();  // Close modal after saving
              })
              .catch(err => {
                alert('Failed to save parameters: ' + err.message);
              });
        });
}

function sortItems(items) {
    return items.sort((a, b) => {
        // Folders first, then files
        if (a.isdir && !b.isdir) return -1;
        if (!a.isdir && b.isdir) return 1;
        // Then alphabetical
        return a.name.localeCompare(b.name);
    });
}

function findLatestFolder(items) {
    const folders = items.filter(item => item.isdir);
    if (folders.length === 0) return null;
    
    // Get the folder that comes last alphabetically (latest timestamp)
    return folders.sort((a, b) => a.name.localeCompare(b.name)).pop();
}

function loadLogFiles() {
    fetch('/list_log_files')
        .then(response => response.json())
        .then(data => {
            const sortedItems = sortItems(data.files);
            const latestFolder = findLatestFolder(sortedItems);
            let html = renderFileTreeWithLatest(sortedItems, latestFolder, showAllLogs);
            document.getElementById('log-files').innerHTML = html;
        });
}

function loadMeasFiles() {
    fetch('/list_meas_files')
        .then(response => response.json())
        .then(data => {
            const sortedItems = sortItems(data.files);
            const latestFolder = findLatestFolder(sortedItems);
            let html = renderFileTreeWithLatest(sortedItems, latestFolder, showAllMeas);
            document.getElementById('meas-files').innerHTML = html;
        });
}

function renderFileTreeWithLatest(items, latestFolder, showAll) {
    let html = '<ul>';
    for (const item of items) {
        const isLatest = latestFolder && item.isdir && item.name === latestFolder.name;
        const shouldHide = !showAll && item.isdir && !isLatest;
        const cssClass = isLatest ? 'latest-folder' : (shouldHide ? 'hidden-folder' : '');
        
        if (item.isdir) {
            const sortedSubItems = item.items ? sortItems(item.items) : [];
            html += `<li class="${cssClass}">
                        <span class="folder-label ${isLatest ? 'open' : ''}" onclick="toggleFolder(event)">${item.name}${isLatest ? ' (Latest)' : ''}</span>
                        <div class="folder-content" style="display:${isLatest ? 'block' : 'none'};">
                            ${renderFileTree(sortedSubItems)}
                        </div>
                     </li>`;
        } else {
            html += `<li class="${cssClass}"><span class="file-label" onclick="showFileContent('${item.path}', '${item.name}')">${item.name}</span></li>`;
        }
    }
    html += '</ul>';
    return html;
}

function renderFileTree(items) {
    let html = '<ul>';
    for (const item of items) {
        if (item.isdir) {
            const sortedSubItems = item.items ? sortItems(item.items) : [];
            html += `<li>
                        <span class="folder-label" onclick="toggleFolder(event)">${item.name}</span>
                        <div class="folder-content" style="display:none;">
                            ${renderFileTree(sortedSubItems)}
                        </div>
                     </li>`;
        } else {
            html += `<li><span class="file-label" onclick="showFileContent('${item.path}', '${item.name}')">${item.name}</span></li>`;
        }
    }
    html += '</ul>';
    return html;
}

function toggleAllFolders(type) {
    if (type === 'log') {
        showAllLogs = !showAllLogs;
        const btn = document.getElementById('toggle-all-logs');
        btn.textContent = showAllLogs ? 'Show Latest Only' : 'Show All Folders';
        loadLogFiles();
    } else if (type === 'meas') {
        showAllMeas = !showAllMeas;
        const btn = document.getElementById('toggle-all-meas');
        btn.textContent = showAllMeas ? 'Show Latest Only' : 'Show All Folders';
        loadMeasFiles();
    }
}

function toggleFolder(event) {
    event.stopPropagation();
    const content = event.target.nextElementSibling;
    if (content.style.display === "none") {
        content.style.display = "block";
        event.target.classList.add('open');
    } else {
        content.style.display = "none";
        event.target.classList.remove('open');
    }
}

function getLanguageFromExtension(filename) {
    if (filename.endsWith('.json')) return 'json';
    if (filename.endsWith('.yaml') || filename.endsWith('.yml')) return 'yaml';
    if (filename.endsWith('.csv')) return 'csv';
    if (filename.endsWith('.py')) return 'python';
    return 'log';
}

function closeFileContent(type) {
    const containerId = type + '-file-content-container';
    document.getElementById(containerId).style.display = 'none';
}

function formatLogContent(text) {
    // Basic log formatting with color coding
    return text.split('\n').map(line => {
        let formattedLine = line;
        
        // Color code different log levels
        if (line.includes('ERROR') || line.includes('[ERROR]')) {
            formattedLine = `<span class="log-error">${line}</span>`;
        } else if (line.includes('WARN') || line.includes('[WARN]') || line.includes('WARNING')) {
            formattedLine = `<span class="log-warning">${line}</span>`;
        } else if (line.includes('INFO') || line.includes('[INFO]')) {
            formattedLine = `<span class="log-info">${line}</span>`;
        } else if (line.includes('DEBUG') || line.includes('[DEBUG]')) {
            formattedLine = `<span class="log-debug">${line}</span>`;
        }
        
        // Highlight timestamps (common patterns)
        formattedLine = formattedLine.replace(
            /(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d{3})?)/g,
            '<span class="log-timestamp">$1</span>'
        );
        
        return formattedLine;
    }).join('\n');
}

function showFileContent(filepath, filename) {
    // Determine which section this file belongs to based on the filepath
    const isLogFile = filepath.includes('/log') || filename.endsWith('.log');
    const containerType = isLogFile ? 'log' : 'meas';
    const containerId = containerType + '-file-content-container';
    const nameId = containerType + '-file-name';
    const bodyId = containerType + '-file-content-body';
    
    // Store filepath for refresh functionality
    document.getElementById(bodyId).dataset.filepath = filepath;
    
    fetch('/file_content?filepath=' + encodeURIComponent(filepath))
        .then(response => response.text())
        .then(text => {
            const nameElem = document.getElementById(nameId);
            const bodyElem = document.getElementById(bodyId);
            const containerElem = document.getElementById(containerId);
            
            nameElem.textContent = filename;
            
            if (filename.endsWith('.log')) {
                // Format as log file
                bodyElem.innerHTML = `<div class="log-content">${formatLogContent(text)}</div>`;
            } else if (filename.endsWith('.json')) {
                // Format as JSON
                try {
                    const parsed = JSON.parse(text);
                    const prettyJson = JSON.stringify(parsed, null, 2);
                    bodyElem.innerHTML = `<div class="json-content"><pre><code class="language-json">${prettyJson}</code></pre></div>`;
                    // Apply syntax highlighting
                    const codeElem = bodyElem.querySelector('code');
                    hljs.highlightElement(codeElem);
                } catch (e) {
                    // If JSON parsing fails, show as plain text
                    bodyElem.innerHTML = `<div class="json-content"><pre><code>${text}</code></pre></div>`;
                }
            } else {
                // Default formatting for other file types
                const lang = getLanguageFromExtension(filename);
                bodyElem.innerHTML = `<div class="json-content"><pre><code class="language-${lang}">${text}</code></pre></div>`;
                const codeElem = bodyElem.querySelector('code');
                hljs.highlightElement(codeElem);
            }
            
            containerElem.style.display = 'block';
            containerElem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        })
        .catch(err => {
            alert("Failed to load file content: " + err.message);
        });
}

// New functions for refresh and delete by date
function refreshLogFiles() {
    fetch('/list_log_files')
        .then(response => response.json())
        .then(data => {
            const sortedItems = sortItems(data.files);
            const latestFolder = findLatestFolder(sortedItems);
            let html = renderFileTreeWithLatest(sortedItems, latestFolder, showAllLogs);
            document.getElementById('log-files').innerHTML = html;
        })
        .catch(err => alert("Failed to refresh log files: " + err.message));
}

function refreshMeasFiles() {
    fetch('/list_meas_files')
        .then(response => response.json())
        .then(data => {
            const sortedItems = sortItems(data.files);
            const latestFolder = findLatestFolder(sortedItems);
            let html = renderFileTreeWithLatest(sortedItems, latestFolder, showAllMeas);
            document.getElementById('meas-files').innerHTML = html;
        })
        .catch(err => alert("Failed to refresh measurement files: " + err.message));
}

function refreshLogFileContent() {
    const bodyElem = document.getElementById('log-file-content-body');
    const filepath = bodyElem.dataset.filepath;
    const filename = document.getElementById('log-file-name').textContent;
    
    if (filepath && filename) {
        showFileContent(filepath, filename); // Reuse showFileContent to maintain formatting
    } else {
        alert("No file selected to refresh");
    }
}

function refreshMeasFileContent() {
    const bodyElem = document.getElementById('meas-file-content-body');
    const filepath = bodyElem.dataset.filepath;
    const filename = document.getElementById('meas-file-name').textContent;
    
    if (filepath && filename) {
        showFileContent(filepath, filename); // Reuse showFileContent to maintain formatting
    } else {
        alert("No file selected to refresh");
    }
}

function deleteLogFoldersByDate() {
    const date = document.getElementById('log-delete-date').value;
    if (!date) {
        alert('Please select a date');
        return;
    }
    if (confirm(`Delete all log folders for ${date}?`)) {
        fetch('/delete_folders_by_date', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `date=${encodeURIComponent(date)}&type=log`
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to delete folders');
            return response.text();
        })
        .then(() => {
            alert('Folders deleted successfully');
            refreshLogFiles();
        })
        .catch(err => alert("Failed to delete log folders: " + err.message));
    }
}

function deleteMeasFoldersByDate() {
    const date = document.getElementById('meas-delete-date').value;
    if (!date) {
        alert('Please select a date');
        return;
    }
    if (confirm(`Delete all measurement folders for ${date}?`)) {
        fetch('/delete_folders_by_date', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `date=${encodeURIComponent(date)}&type=meas`
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to delete folders');
            return response.text();
        })
        .then(() => {
            alert('Folders deleted successfully');
            refreshMeasFiles();
        })
        .catch(err => alert("Failed to delete measurement folders: " + err.message));
    }
}

loadStatusAndNodes();
loadParameters();
loadLogFiles();
loadMeasFiles();
setInterval(loadStatusAndNodes, 2000);

document.addEventListener("DOMContentLoaded", function() {
    const runBtn = document.getElementById("run-service-btn");
    if (runBtn) {
        runBtn.onclick = function() {
            fetch('/run_main_service', {
                method: 'POST'
            })
            .then(response => response.text())
            .then(msg => alert(msg))
            .catch(err => alert("Failed to run service: " + err.message));
        }
    }
});
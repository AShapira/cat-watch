# Dot-source after cat-watch.ps1 declares DataRoot. No service mutation.
function Get-LabelingMounts {
    $private = Join-Path $DataRoot 'cat-watch-label-studio\private'
    $config = Join-Path $private 'integration.json'
    if (!(Test-Path $config)) { return @() }
    $dataset = Join-Path $DataRoot 'cat-watch-dataset'
    return @('--mount',"type=bind,source=$dataset,target=/dataset",
             '--mount',"type=bind,source=$private,target=/labeling-private,ro=true",
             '--env','CATWATCH_LABELING_CONFIG=/labeling-private/integration.json')
}

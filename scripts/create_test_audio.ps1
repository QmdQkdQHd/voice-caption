$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$fixtureDir = Join-Path $PSScriptRoot '..\build\fixtures'
New-Item -ItemType Directory -Force -Path $fixtureDir | Out-Null
$fixturePath = [System.IO.Path]::GetFullPath((Join-Path $fixtureDir 'english-test.wav'))
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $english = $speaker.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*'
    } | Select-Object -First 1
    if (-not $english) { throw 'An English Windows speech synthesis voice is required.' }
    $speaker.SelectVoice($english.VoiceInfo.Name)
    $speaker.Rate = -1
    $speaker.SetOutputToWaveFile($fixturePath)
    $speaker.Speak('Hello team. Are you ready?')
} finally {
    $speaker.Dispose()
}
Write-Output "Created synthetic English test audio: $fixturePath"
if ($env:GITHUB_ENV) {
    "VOICE_CAPTION_TEST_AUDIO=$fixturePath" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
}

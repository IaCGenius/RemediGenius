/**
 * lambda-kiosk: lets agents build, test, promote and run their own Lambda functions, inside limits they
 * cannot change. Reusable: nothing here knows about RemediGenius.
 *
 *   gate (Step Functions + gate Lambda)   validate -> sandbox tests -> sign -> deploy (version + alias dev)
 *   promote (Step Functions)              canary run -> live alias; rollback; retire
 *   run (Step Functions)                  Map over units -> function alias -> receipt (auto-rollback)
 *   registry, events, receipts            S3 bucket kiosk-<name>-<account>-<region>
 *   config + freeze switch                SSM /kiosk/<name>/config, /kiosk/<name>/frozen
 *
 * Build the zips first: python build.py (tf.sh does it before every kiosk plan).
 */
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
}

locals {
  prefix          = "kiosk-${var.name}"
  bucket          = "${local.prefix}-${var.account_id}-${var.region}"
  function_prefix = "${local.prefix}-fn-"
  fn_arn          = "arn:aws:lambda:${var.region}:${var.account_id}:function:${local.function_prefix}"
  param_prefix    = "/kiosk/${var.name}"
  build           = "${path.module}/build"
  classes = {
    isolated  = "No AWS access: pure computation on the unit it is given"
    processor = "Reads and writes the agent's own outputs/ prefix in the kiosk bucket; no other AWS access"
  }
  agent_classes = { for pair in flatten([for a, v in var.agents : [for c in v.classes : { agent = a, class = c }]]) :
  "${pair.agent}/${pair.class}" => pair }
  machines = ["gate", "promote", "run"]
}

# ---------------------------------------------------------------- bucket: incoming, bundles, signed, registry, events, runs, outputs
resource "aws_s3_bucket" "kiosk" {
  bucket        = local.bucket
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_versioning" "kiosk" { # AWS Signer needs a versioned source
  bucket = aws_s3_bucket.kiosk.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "kiosk" {
  bucket = aws_s3_bucket.kiosk.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "kiosk" {
  bucket                  = aws_s3_bucket.kiosk.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "kiosk" {
  bucket = aws_s3_bucket.kiosk.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.kiosk.arn, "${aws_s3_bucket.kiosk.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.kiosk]
}

resource "aws_s3_bucket_lifecycle_configuration" "kiosk" {
  bucket = aws_s3_bucket.kiosk.id
  rule {
    id     = "incoming-7d"
    status = "Enabled"
    filter { prefix = "incoming/" }
    expiration { days = 7 }
  }
  rule {
    id     = "events-90d"
    status = "Enabled"
    filter { prefix = "events/" }
    expiration { days = 90 }
  }
  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 30 }
    abort_incomplete_multipart_upload { days_after_initiation = 2 }
  }
}

# ---------------------------------------------------------------- code signing: only the gate's signed code deploys
resource "aws_signer_signing_profile" "kiosk" {
  name        = replace("kiosk_${var.name}", "-", "_")
  platform_id = "AWSLambda-SHA384-ECDSA"
  signature_validity_period {
    value = 5
    type  = "YEARS"
  }
}

resource "aws_lambda_code_signing_config" "kiosk" {
  description = "${local.prefix}: only code signed by the kiosk gate"
  allowed_publishers {
    signing_profile_version_arns = [aws_signer_signing_profile.kiosk.version_arn]
  }
  policies { untrusted_artifact_on_deployment = "Enforce" }
}

# ---------------------------------------------------------------- layers (pinned, built by build.py)
# The code signing config (Enforce) also checks layers, so the runtime layer that every agent function
# uses is signed with the kiosk's own profile: upload, sign, publish from the signed object.
resource "aws_s3_object" "runtime_layer" {
  bucket      = aws_s3_bucket.kiosk.id
  key         = "platform/layers/runtime-layer.zip"
  source      = "${local.build}/runtime-layer.zip"
  source_hash = filemd5("${local.build}/runtime-layer.zip")
  depends_on  = [aws_s3_bucket_versioning.kiosk]
}

resource "aws_signer_signing_job" "runtime_layer" {
  profile_name = aws_signer_signing_profile.kiosk.name
  source {
    s3 {
      bucket  = aws_s3_bucket.kiosk.id
      key     = aws_s3_object.runtime_layer.key
      version = aws_s3_object.runtime_layer.version_id
    }
  }
  destination {
    s3 {
      bucket = aws_s3_bucket.kiosk.id
      prefix = "platform/signed/"
    }
  }
  ignore_signing_job_failure = false
}

resource "aws_lambda_layer_version" "runtime" {
  layer_name               = "${local.prefix}-runtime"
  description              = "kiosk_runtime + pinned boto3/botocore (layers/runtime.lock), signed"
  s3_bucket                = aws_signer_signing_job.runtime_layer.signed_object[0].s3[0].bucket
  s3_key                   = aws_signer_signing_job.runtime_layer.signed_object[0].s3[0].key
  source_code_hash         = filebase64sha256("${local.build}/runtime-layer.zip")
  compatible_runtimes      = [var.runtime]
  compatible_architectures = ["x86_64"]
}

resource "aws_lambda_layer_version" "test" {
  layer_name               = "${local.prefix}-test"
  description              = "pytest (layers/test.lock) for the sandbox and kiosk test"
  filename                 = "${local.build}/test-layer.zip"
  source_code_hash         = filebase64sha256("${local.build}/test-layer.zip")
  compatible_runtimes      = [var.runtime]
  compatible_architectures = ["x86_64"]
}

# ---------------------------------------------------------------- config + freeze switch
resource "aws_ssm_parameter" "config" {
  name  = "${local.param_prefix}/config"
  type  = "String"
  tier  = "Intelligent-Tiering"
  value = jsonencode(local.config)
}

resource "aws_ssm_parameter" "frozen" {
  name        = "${local.param_prefix}/frozen"
  type        = "String"
  value       = "false"
  description = "Admin switch: true = no submissions or promotions; runs use live versions only"
  lifecycle { ignore_changes = [value] }
}

locals {
  config = {
    name                = var.name
    region              = var.region
    bucket              = local.bucket
    function_prefix     = local.function_prefix
    runtime             = var.runtime
    log_retention_days  = var.log_retention_days
    code_signing_config = aws_lambda_code_signing_config.kiosk.arn
    state_machines      = { for m in local.machines : m => aws_sfn_state_machine.m[m].arn }
    layers              = { runtime = aws_lambda_layer_version.runtime.arn, test = aws_lambda_layer_version.test.arn }
    limits              = var.limits
    kits                = ["hello", "processor", "python-blank"]
    compute             = ["lambda"]
    classes = { for c, d in local.classes : c => {
      description = d
      role_arns   = { for k, p in local.agent_classes : p.agent => aws_iam_role.class[k].arn if p.class == c }
    } }
    agents = { for a, v in var.agents : a => {
      classes  = v.classes
      policy   = v.promotion_policy
      role_arn = aws_iam_role.agent[a].arn
    } }
  }
}

# ---------------------------------------------------------------- IAM: execution classes (one role per agent x class)
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "class" {
  for_each           = local.agent_classes
  name               = "${local.prefix}-${each.value.agent}-${each.value.class}"
  description        = "Kiosk class ${each.value.class} for agent ${each.value.agent}: ${local.classes[each.value.class]}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "class" {
  for_each = local.agent_classes
  name     = "class"
  role     = aws_iam_role.class[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid      = "OwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${local.function_prefix}${each.value.agent}-*:*"]
      }],
      [for st in [
        {
          Sid      = "OwnOutputs"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject"]
          Resource = ["${aws_s3_bucket.kiosk.arn}/outputs/${each.value.agent}/*"]
        },
        {
          Sid       = "ListOwnOutputs"
          Effect    = "Allow"
          Action    = ["s3:ListBucket"]
          Resource  = [aws_s3_bucket.kiosk.arn]
          Condition = { StringLike = { "s3:prefix" = ["outputs/${each.value.agent}/*"] } }
      }] : st if each.value.class == "processor"]
    )
  })
}

# ---------------------------------------------------------------- IAM: agent roles (what an agent may ask for)
resource "aws_iam_role" "agent" {
  for_each             = var.agents
  name                 = "${local.prefix}-agent-${each.key}"
  description          = "Kiosk agent ${each.key}: submit bundles, start gate/promote/run, read registry and own outputs"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = each.value.trusted_principal_arns }
      Action    = ["sts:AssumeRole", "sts:SetSourceIdentity"]
    }]
  })
}

resource "aws_iam_role_policy" "agent" {
  for_each = var.agents
  name     = "agent"
  role     = aws_iam_role.agent[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SubmitOwnBundles"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.kiosk.arn}/incoming/${each.key}/*"]
      },
      {
        Sid    = "ReadRegistryRunsOwnOutputs"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.kiosk.arn}/registry/*", "${aws_s3_bucket.kiosk.arn}/runs/*",
        "${aws_s3_bucket.kiosk.arn}/outputs/${each.key}/*"]
      },
      {
        Sid       = "ListRegistryRunsOwnOutputs"
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = [aws_s3_bucket.kiosk.arn]
        Condition = { StringLike = { "s3:prefix" = ["registry/*", "runs/*", "outputs/${each.key}/*"] } }
      },
      {
        Sid      = "StartKioskMachines"
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [for m in local.machines : aws_sfn_state_machine.m[m].arn]
      },
      {
        Sid      = "WatchKioskExecutions"
        Effect   = "Allow"
        Action   = ["states:DescribeExecution", "states:GetExecutionHistory"]
        Resource = [for m in local.machines : "arn:aws:states:${var.region}:${var.account_id}:execution:${local.prefix}-${m}:*"]
      },
      {
        Sid      = "ReadKioskConfig"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = ["arn:aws:ssm:${var.region}:${var.account_id}:parameter${local.param_prefix}/*"]
      },
      {
        Sid      = "DownloadPinnedLayers"
        Effect   = "Allow"
        Action   = ["lambda:GetLayerVersion"]
        Resource = [aws_lambda_layer_version.runtime.arn, aws_lambda_layer_version.test.arn]
      },
      {
        Sid    = "ReadOwnFunctionLogs"
        Effect = "Allow"
        Action = ["logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogStreams"]
        Resource = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${local.function_prefix}${each.key}-*",
        "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${local.function_prefix}${each.key}-*:*"]
      },
      {
        # Only the gate creates or changes functions; agents never invoke them directly (runs go through the run machine).
        Sid    = "NeverDirect"
        Effect = "Deny"
        Action = ["lambda:CreateFunction", "lambda:UpdateFunction*", "lambda:DeleteFunction*", "lambda:PublishVersion",
          "lambda:CreateAlias", "lambda:UpdateAlias", "lambda:DeleteAlias", "lambda:AddPermission", "lambda:InvokeFunction",
        "lambda:PutFunction*", "iam:*", "ssm:PutParameter", "ssm:DeleteParameter*", "signer:*", "states:StopExecution"]
        Resource = "*"
      }
    ]
  })
}

# ---------------------------------------------------------------- IAM: gate
resource "aws_iam_role" "gate" {
  name               = "${local.prefix}-gate"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "gate" {
  name = "gate"
  role = aws_iam_role.gate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "OwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.gate.arn}:*"]
      },
      {
        Sid      = "FunctionLogGroups"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:PutRetentionPolicy"]
        Resource = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${local.function_prefix}*"]
      },
      {
        Sid      = "Bucket"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.kiosk.arn}/*"]
      },
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:ListBucketVersions"]
        Resource = [aws_s3_bucket.kiosk.arn]
      },
      {
        Sid      = "Sign"
        Effect   = "Allow"
        Action   = ["signer:StartSigningJob", "signer:GetSigningProfile"]
        Resource = [aws_signer_signing_profile.kiosk.arn]
      },
      {
        Sid      = "SignStatus"
        Effect   = "Allow"
        Action   = ["signer:DescribeSigningJob"]
        Resource = "*"
      },
      {
        Sid       = "CreateOnlySigned"
        Effect    = "Allow"
        Action    = ["lambda:CreateFunction"]
        Resource  = ["${local.fn_arn}*"]
        Condition = { StringEquals = { "lambda:CodeSigningConfigArn" = aws_lambda_code_signing_config.kiosk.arn } }
      },
      {
        Sid    = "ManageKioskFunctions"
        Effect = "Allow"
        Action = ["lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration", "lambda:PublishVersion",
          "lambda:CreateAlias", "lambda:UpdateAlias", "lambda:GetAlias", "lambda:GetFunction", "lambda:GetFunctionConfiguration",
          "lambda:PutFunctionConcurrency", "lambda:TagResource", "lambda:InvokeFunction", "lambda:ListVersionsByFunction",
        "lambda:GetFunctionCodeSigningConfig"]
        Resource = ["${local.fn_arn}*"]
      },
      {
        Sid      = "CodeSigningConfig"
        Effect   = "Allow"
        Action   = ["lambda:GetCodeSigningConfig"]
        Resource = [aws_lambda_code_signing_config.kiosk.arn]
      },
      {
        Sid      = "InvokeSandbox"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = [aws_lambda_function.sandbox.arn]
      },
      {
        Sid      = "UseLayers"
        Effect   = "Allow"
        Action   = ["lambda:GetLayerVersion"]
        Resource = [aws_lambda_layer_version.runtime.arn]
      },
      {
        Sid       = "PassClassRolesToLambdaOnly"
        Effect    = "Allow"
        Action    = ["iam:PassRole"]
        Resource  = [for r in aws_iam_role.class : r.arn]
        Condition = { StringEquals = { "iam:PassedToService" = "lambda.amazonaws.com" } }
      },
      {
        Sid      = "ReadConfig"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = [aws_ssm_parameter.config.arn, aws_ssm_parameter.frozen.arn]
      },
      {
        Sid      = "Alert"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "gate" {
  name              = "/aws/lambda/${local.prefix}-gate"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "gate" {
  function_name    = "${local.prefix}-gate"
  description      = "Kiosk gate: the only code that creates or changes kiosk functions"
  role             = aws_iam_role.gate.arn
  runtime          = var.runtime
  handler          = "gate.handler"
  filename         = "${local.build}/gate.zip"
  source_code_hash = filebase64sha256("${local.build}/gate.zip")
  layers           = [aws_lambda_layer_version.runtime.arn]
  timeout          = 360
  memory_size      = 512
  architectures    = ["x86_64"]
  environment {
    variables = {
      KIOSK_BUCKET          = aws_s3_bucket.kiosk.id
      KIOSK_CONFIG_PARAM    = "${local.param_prefix}/config" # by name: the config itself names the state machines
      KIOSK_FROZEN_PARAM    = "${local.param_prefix}/frozen"
      KIOSK_SANDBOX_FN      = aws_lambda_function.sandbox.function_name
      KIOSK_SIGNING_PROFILE = aws_signer_signing_profile.kiosk.name
      KIOSK_ALERT_TOPIC     = aws_sns_topic.alerts.arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.gate]
}

# ---------------------------------------------------------------- sandbox: tests only, no network, no rights
resource "aws_iam_role" "sandbox" {
  name               = "${local.prefix}-sandbox"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "sandbox_vpc" { # logs + network interfaces in its subnet; nothing else
  role       = aws_iam_role.sandbox.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_cloudwatch_log_group" "sandbox" {
  name              = "/aws/lambda/${local.prefix}-sandbox"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "sandbox" {
  function_name                  = "${local.prefix}-sandbox"
  description                    = "Kiosk sandbox: runs bundle tests offline with dummy credentials"
  role                           = aws_iam_role.sandbox.arn
  runtime                        = var.runtime
  handler                        = "sandbox.main"
  filename                       = "${local.build}/sandbox.zip"
  source_code_hash               = filebase64sha256("${local.build}/sandbox.zip")
  layers                         = [aws_lambda_layer_version.runtime.arn, aws_lambda_layer_version.test.arn]
  timeout                        = 300
  memory_size                    = 1024
  architectures                  = ["x86_64"]
  reserved_concurrent_executions = 2
  vpc_config {
    subnet_ids         = var.sandbox_subnet_ids
    security_group_ids = var.sandbox_security_group_ids
  }
  depends_on = [aws_cloudwatch_log_group.sandbox, aws_iam_role_policy_attachment.sandbox_vpc]
}

# ---------------------------------------------------------------- state machines: gate, promote, run
resource "aws_iam_role" "sfn" {
  name = "${local.prefix}-sfn"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "sfn" {
  name = "invoke"
  role = aws_iam_role.sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeGateAndKioskFunctions"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [aws_lambda_function.gate.arn, "${local.fn_arn}*"]
    }]
  })
}

resource "aws_sfn_state_machine" "m" {
  for_each   = toset(local.machines)
  name       = "${local.prefix}-${each.key}"
  role_arn   = aws_iam_role.sfn.arn
  definition = templatefile("${path.module}/statemachines/${each.key}.asl.json", { gate = aws_lambda_function.gate.arn })
}

# ---------------------------------------------------------------- alerts: platform faults reach the admin without Hermes
resource "aws_sns_topic" "alerts" {
  name = "${local.prefix}-alerts"
}

resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EventBridgePublish"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.alerts.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.failed.arn } }
    }]
  })
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_event_rule" "failed" {
  name        = "${local.prefix}-failed"
  description = "A kiosk state machine execution failed, timed out or was aborted (platform fault)"
  event_pattern = jsonencode({
    source        = ["aws.states"]
    "detail-type" = ["Step Functions Execution Status Change"]
    detail = {
      status          = ["FAILED", "TIMED_OUT", "ABORTED"]
      stateMachineArn = [for m in local.machines : aws_sfn_state_machine.m[m].arn]
    }
  })
}

resource "aws_cloudwatch_event_target" "failed" {
  rule = aws_cloudwatch_event_rule.failed.name
  arn  = aws_sns_topic.alerts.arn
}

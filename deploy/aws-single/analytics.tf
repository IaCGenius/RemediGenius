# Standard historical analytics path. The agent never receives this role's credentials.
resource "aws_athena_workgroup" "analytics" {
  name = "${var.name}-analytics"
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 104857600
    engine_version { selected_engine_version = "Athena engine version 3" }
    result_configuration {
      output_location       = "s3://${aws_s3_bucket.data.id}/analytics-results/"
      expected_bucket_owner = var.account_id
      encryption_configuration { encryption_option = "SSE_S3" }
    }
  }
}

resource "aws_iam_role" "analytics" {
  name = "${var.name}-analytics"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { AWS = aws_iam_role.host.arn }, Action = "sts:AssumeRole"
  }] })
}

resource "aws_iam_role_policy" "analytics" {
  name = "CEWarehouseAnalytics"
  role = aws_iam_role.analytics.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"], Resource = aws_athena_workgroup.analytics.arn },
    { Effect = "Allow", Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"], Resource = [
      "arn:aws:glue:${var.region}:${var.account_id}:catalog",
      "arn:aws:glue:${var.region}:${var.account_id}:database/${aws_glue_catalog_database.ce.name}",
      "arn:aws:glue:${var.region}:${var.account_id}:table/${aws_glue_catalog_database.ce.name}/*"
    ] },
    { Effect = "Allow", Action = "s3:GetBucketLocation", Resource = aws_s3_bucket.data.arn },
    { Effect = "Allow", Action = "s3:ListBucket", Resource = aws_s3_bucket.data.arn,
    Condition = { StringLike = { "s3:prefix" = ["warehouse/*", "analytics-results/*"] } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = ["${aws_s3_bucket.data.arn}/warehouse/*", "${aws_s3_bucket.data.arn}/analytics-results/*"] },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:AbortMultipartUpload"], Resource = "${aws_s3_bucket.data.arn}/analytics-results/*" }
  ] })
}

resource "aws_iam_role_policy" "analytics_assume" {
  name = "CEAnalyticsAssume"
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Resource = aws_iam_role.analytics.arn
  }] })
}

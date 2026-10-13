# AWS deployment preparation (Phase 11)

**Status: preparation only. Nothing has been deployed, no AWS account was used, and no costs were
incurred.** This document records the intended architecture, security controls, cost method and
cleanup procedure so a deployment can be done deliberately later. Prices are deliberately not
quoted here; they change and must be taken from the AWS Pricing Calculator for the chosen region.

## Principle

Deploy only after the local system is reliable (plan §29, Phase 11) and only the minimum needed.
Managed services are options, not requirements.

## What actually needs to run

| Workload | Resource need (measured or reasoned) | Smallest sensible option |
|---|---|---|
| Depth recorder | tiny CPU/RAM, stdlib only, outbound HTTPS | one small EC2 instance (or an ECS/Fargate task) |
| API + dashboard | light; read files and run short backtests | same instance via Docker Compose |
| Data volume | about 250 MB/day for BTC/USDT, 3 exchanges, 1 s (measured); about 0.75 GB/day for three symbols | one EBS volume, 7-day raw retention |
| Research job | CPU-heavy for minutes (the synthetic experiment run takes about 9 minutes on a laptop) | run on demand, then stop |

A single EC2 instance running the existing Docker Compose stack is enough for the research phase.
ECS, an Application Load Balancer, RDS and ElastiCache add cost and operations work without a
current benefit because the application does not use PostgreSQL or Redis yet.

## Recommended minimal architecture

```text
VPC (one region)
 |- public subnet:  EC2 instance (Docker Compose), Elastic IP not required
 |       - security group: inbound none, or SSH/SSM from your IP only
 |       - dashboard/API reached through SSM port forwarding, not the internet
 |- EBS gp3 volume for /var/lib/docker volumes (encrypted)
 |- CloudWatch agent: container logs + disk/CPU alarms
 |- S3 bucket (private, encrypted, lifecycle rule): compressed daily archives of raw data
 '- AWS Budgets + billing alarm
```

Optional later: RDS PostgreSQL in private subnets (only once application code writes to it),
ElastiCache Redis (only if a latency-sensitive cache is needed).

## Security checklist

- [ ] IAM: dedicated role for the instance with least privilege (S3 prefix write, CloudWatch logs);
  no long-lived access keys on the machine; MFA on the human account.
- [ ] No exchange API keys at all (public endpoints only); no trading permissions.
- [ ] Security group with no public inbound; management through SSM Session Manager.
- [ ] Databases (if added) in private subnets, no public access, restricted security groups.
- [ ] Secrets in AWS Secrets Manager or SSM Parameter Store, not in the image or repository.
- [ ] Encrypt EBS and S3; block public access on the bucket.
- [ ] Keep the compose rule that published ports bind to loopback only.
- [ ] Review exposure (open ports, public buckets) before and after deployment.
- [ ] Update base images and dependencies on a schedule.

## Cost control

1. Estimate in the AWS Pricing Calculator for: one small instance running continuously, EBS storage
   sized for the retention policy (raw 7 days x measured GB/day, plus a margin), data transfer out
   (should be near zero), S3 storage for archives, CloudWatch logs and alarms.
2. Create an AWS Budget with email alerts at, for example, 50 %, 80 % and 100 % of the monthly limit
   and enable billing alerts before launching anything.
3. Tag every resource (`project=crypto-arbitrage`) so costs can be filtered and cleanup is complete.
4. Stop the instance when not collecting; run the research job on demand.
5. Apply S3 lifecycle rules (expire raw archives per policy).
6. Review Cost Explorer weekly during the first month.

## Deployment steps (when approved)

1. Build and push images to a private registry (or build on the instance).
2. Launch the instance with the instance profile and an encrypted volume; attach to SSM.
3. Clone the repository, create `.env` from `.env.example`, run `python scripts/check_env.py`.
4. `docker compose up -d --build`; confirm `docker compose ps` shows all services healthy.
5. Forward ports through SSM, open the dashboard, run `scripts/data_quality_report.py` after an hour.
6. Verify recovery: reboot the instance, confirm the collector resumes appending (restart-safe by
   design: files are appended and runs are separated by `run_id`).

## Cleanup (delete everything this project created)

1. `docker compose down` (add `-v` only after archiving data you want to keep).
2. Terminate the instance; delete the EBS volume and snapshots.
3. Empty and delete the S3 bucket; delete CloudWatch log groups.
4. Delete IAM roles/policies, security groups, VPC components and any Elastic IPs.
5. Remove tagged resources with a tag search (`project=crypto-arbitrage`) to catch leftovers.
6. Check the next day's Cost Explorer and keep the budget alarm for one more billing cycle.

## Not decided or verified

Region, instance size, monthly budget and whether to use S3 archives are open decisions. The
numbers above come from a 15-minute local sample and must be re-measured after the 3-7 day run.

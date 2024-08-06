#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { ServerlessPdfChatStack } from '../lib/serverless-pdf-stack';

const app = new cdk.App();

const env = { 
  account: process.env.CDK_DEFAULT_ACCOUNT, 
  region: 'us-west-2' 
};

new ServerlessPdfChatStack(app, 'ServerlessPdfChatStack', { env });